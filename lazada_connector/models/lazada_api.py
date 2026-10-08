import hashlib
import hmac
import json
import logging
import time
import urllib.parse
from datetime import datetime, timezone
from xml.etree import ElementTree

import requests

_logger = logging.getLogger(__name__)

# Lazada API hosts are region specific. Lazada has no separate "sandbox"
# domain - testing is done against the normal regional/auth hosts using a
# test seller account (see Loan Test Account in the Open Platform console).
REGION_HOSTS = {
    "th": "https://api.lazada.co.th/rest",
    "sg": "https://api.lazada.sg/rest",
    "my": "https://api.lazada.com.my/rest",
    "id": "https://api.lazada.co.id/rest",
    "ph": "https://api.lazada.com.ph/rest",
    "vn": "https://api.lazada.vn/rest",
    "cb": "https://api.lazada.com/rest",
}
AUTH_BASE = "https://auth.lazada.com"
# Token create/refresh live under /rest on the auth host; the browser-facing
# /oauth/authorize page does not use the /rest prefix.
AUTH_REST_BASE = "https://auth.lazada.com/rest"

_MASK_KEYS = ("app_secret", "access_token", "sign", "refresh_token", "code",
              "webhook_secret", "authorization", "oauth_state", "temp_auth_code",
              "temp_access_token", "temp_refresh_token")
_MAX_LIST = 50
_MAX_DOCUMENT_BYTES = 20 * 1024 * 1024


def _iso8601(value):
    """Lazada date filters take ISO 8601; naive datetimes are Odoo UTC."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat(timespec="seconds")
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc).isoformat(
            timespec="seconds"
        )
    return str(value)


def _numeric(value):
    """Send numeric ids as JSON numbers, like Lazada's examples."""
    return int(value) if str(value).isdigit() else value


class LazadaAPIError(Exception):
    """Raised when Lazada returns a non-zero ``code`` field."""

    def __init__(self, error, message="", request_id="", error_type=""):
        self.error = error
        self.message = message
        self.request_id = request_id
        # Lazada's ``type``: ISV = caller error, ISP/SYSTEM = platform error.
        self.error_type = error_type
        super().__init__(
            f"Lazada API error [{error}]: {message or '(no message)'}"
            + (f" (request_id={request_id})" if request_id else "")
        )


def _mask(params):
    return _mask_value(params or {})


def _mask_value(value):
    if isinstance(value, dict):
        return {
            key: ("***" if str(key).lower() in _MASK_KEYS and item else _mask_value(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_mask_value(item) for item in value]
    return value


class LazadaAPI:
    """Thin wrapper around the Lazada Open Platform REST API.
    Not an Odoo model - instantiate from a lazada.config record.
    """

    def __init__(
        self, app_key, app_secret, region="th", environment="production",
        log_callback=None,
    ):
        self.app_key = str(app_key).strip()
        self.app_secret = str(app_secret).strip()
        self.region = str(region or "th").strip()
        self.environment = environment
        self.host = REGION_HOSTS.get(self.region) or REGION_HOSTS["cb"]
        self.log_callback = log_callback

    # ------------------------------------------------------------------
    # Signing
    # ------------------------------------------------------------------
    def _sign(self, path, params):
        """Lazada signature.

        base = path + sorted(key + value) concatenation of every request
        parameter (excluding ``sign`` itself). Signed with HMAC-SHA256 using
        the app secret; result is the uppercase hex digest.
        """
        filtered = {
            k: v for k, v in (params or {}).items()
            if k != "sign" and v is not None
        }
        base = path + "".join(
            f"{key}{filtered[key]}" for key in sorted(filtered)
        )
        return hmac.new(
            self.app_secret.encode(), base.encode(), hashlib.sha256
        ).hexdigest().upper()

    # ------------------------------------------------------------------
    # Core request
    # ------------------------------------------------------------------
    def _request(self, method, path, access_token="", params=None,
                 is_public=False, retries=3, raw=False):
        """Single entry point for every Lazada call.

        Common params (app_key, timestamp in ms, sign_method, access_token
        for user calls, sign) go in the query string. Business params go in
        the query string for GET and in the form body for POST, like
        Lazada's official SDK; every param is signed together.
        Retries on connection errors / 5xx up to ``retries`` times; never
        retries a 4xx or a Lazada business error. ``raw`` returns the whole
        response instead of its ``data`` member.
        """
        query = {
            "app_key": self.app_key,
            "sign_method": "sha256",
            "timestamp": int(time.time() * 1000),
        }
        if not is_public and access_token:
            query["access_token"] = access_token
        business = dict(params or {})
        query["sign"] = self._sign(path, dict(query, **business))
        body = None
        if method == "GET":
            query.update(business)
        else:
            body = business

        # Token creation/refresh always live on the auth host, regardless
        # of region - every other endpoint uses the regional API host.
        base = AUTH_REST_BASE if path.startswith("/auth/") else self.host
        url = f"{base}{path}"
        _logger.debug("Lazada %s %s params=%s body=%s",
                      method, path, _mask(query), _mask(body))

        started = time.monotonic()
        delay = 0.5
        last_exc = None
        for attempt in range(retries):
            if attempt:
                time.sleep(delay)
                delay *= 2
            try:
                resp = requests.request(
                    method, url, params=query, data=body, timeout=30
                )
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_exc = exc
                _logger.warning("Lazada %s %s network error (try %s): %s",
                                method, path, attempt + 1, type(exc).__name__)
                continue

            if resp.status_code >= 500:
                last_exc = requests.HTTPError(f"HTTP {resp.status_code}", response=resp)
                _logger.warning("Lazada %s %s HTTP %s (try %s)",
                                method, path, resp.status_code, attempt + 1)
                continue

            try:
                data = resp.json()
            except ValueError:
                data = None
            if resp.status_code >= 400:
                message = (data or {}).get("message") if isinstance(data, dict) else resp.text[:500]
                error = (data or {}).get("code") if isinstance(data, dict) else None
                exc = LazadaAPIError(error or f"http_{resp.status_code}", message or "")
                self._write_log(
                    method, path, query, body, data or resp.text[:500],
                    "error", resp.status_code, started, exc,
                )
                raise exc
            if data is None:
                exc = LazadaAPIError("non_json_response", resp.text[:500])
                self._write_log(
                    method, path, query, body, resp.text[:500],
                    "error", resp.status_code, started, exc,
                )
                raise exc
            if not isinstance(data, dict):
                exc = LazadaAPIError("invalid_response", "Expected a JSON object.")
                self._write_log(
                    method, path, query, body, data,
                    "error", resp.status_code, started, exc,
                )
                raise exc

            code = str(data.get("code", "0"))
            if code not in ("0", 0):
                exc = LazadaAPIError(
                    code,
                    data.get("message", ""),
                    data.get("request_id", ""),
                    data.get("type", ""),
                )
                self._write_log(
                    method, path, query, body, data, "error",
                    resp.status_code, started, exc,
                )
                raise exc
            self._write_log(
                method, path, query, body, data, "success",
                resp.status_code, started, None,
            )
            # OAuth responses put tokens at the top level; business APIs
            # normally wrap their payload in "data", fulfillment APIs in
            # "result".
            if raw or path in ("/auth/token/create", "/auth/token/refresh"):
                return data
            return data.get("data") or {}

        exc = LazadaAPIError("network", type(last_exc).__name__)
        self._write_log(
            method, path, query, body, None, "error", 0, started, exc,
        )
        raise exc

    def _write_log(
        self, method, path, params, body, response, status,
        http_status, started, error,
    ):
        if not self.log_callback:
            return
        try:
            request_data = {"params": _mask(params)}
            if body:
                request_data["body"] = _mask(body)
            self.log_callback(
                http_method=method,
                endpoint=path,
                request_data=request_data,
                response_data=_mask_value(response),
                status=status,
                http_status=http_status,
                duration_ms=int((time.monotonic() - started) * 1000),
                error_message=str(error) if error else False,
            )
        except Exception:
            _logger.exception("Unable to write Lazada API log")

    def _get(self, path, access_token, params=None):
        return self._request("GET", path, access_token, params=params)

    def _post(self, path, access_token, params=None, is_public=False):
        return self._request(
            "POST", path, access_token, params=params, is_public=is_public
        )

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------
    def get_authorization_url(self, redirect_url, state=None):
        return (
            f"{AUTH_BASE}/oauth/authorize?response_type=code&force_auth=true"
            f"&client_id={urllib.parse.quote(self.app_key, safe='')}"
            f"&redirect_uri={urllib.parse.quote(redirect_url, safe='')}"
            f"&country={urllib.parse.quote(self.region, safe='')}"
            + (f"&state={urllib.parse.quote(str(state), safe='')}" if state else "")
        )

    def get_access_token(self, code):
        # Lazada's OAuth documentation defines token creation as a GET with
        # the one-time code in the query string. This also avoids sending the
        # code in a POST body while the signed request carries it in the URL.
        return self._get(
            "/auth/token/create", access_token="", params={"code": code}
        )

    def refresh_access_token(self, refresh_token):
        return self._post(
            "/auth/token/refresh", access_token="",
            params={"refresh_token": refresh_token}, is_public=True,
        )

    # ------------------------------------------------------------------
    # Seller
    # ------------------------------------------------------------------
    def get_seller_info(self, access_token):
        return self._get("/seller/get", access_token)

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------
    def get_orders(self, access_token, created_after, created_before=None,
                   offset=0, limit=50):
        """``created_after``/``created_before``: datetime (naive = UTC) or
        epoch seconds; sent as ISO 8601 as Lazada requires."""
        params = {
            "created_after": _iso8601(created_after),
            "offset": int(offset),
            "limit": int(limit),
            "sort_by": "created_at",
            "sort_direction": "DESC",
        }
        if created_before:
            params["created_before"] = _iso8601(created_before)
        return self._get("/orders/get", access_token, params)

    def get_order(self, access_token, order_id):
        return self._get(
            "/order/get", access_token, {"order_id": str(order_id)}
        )

    def get_order_items(self, access_token, order_id):
        return self._get(
            "/order/items/get", access_token, {"order_id": str(order_id)}
        )

    def get_finance_transactions(self, access_token, order_id, start_date, end_date,
                                 limit=500):
        """Finance transactions (item credit, shipping, fees) of one order.

        Lazada's QueryTransactionDetails needs a date range (YYYY-MM-DD);
        rows carry ``amount``, ``fee_name``, ``fee_type`` and
        ``transaction_type``. Transactions appear once Lazada settles them.
        """
        data = self._get("/finance/transaction/details/get", access_token, {
            "trade_order_id": str(order_id),
            "start_time": str(start_date),
            "end_time": str(end_date),
            "offset": 0,
            "limit": int(limit),
        })
        if isinstance(data, dict):
            data = data.get("transactions") or data.get("data") or []
        return data if isinstance(data, list) else []

    def get_order_status(self, access_token, order_id):
        """Return current order details, including the statuses field."""
        return self.get_order(access_token, order_id)

    # ------------------------------------------------------------------
    # Products / Stock
    # ------------------------------------------------------------------
    def get_products(self, access_token, offset=0, limit=50):
        params = {
            "filter": "live",
            "offset": int(offset),
            "limit": int(limit),
        }
        return self._get("/products/get", access_token, params)

    @staticmethod
    def _price_quantity_payload(rows):
        """XML ``payload`` of ``product/price_quantity/update``.

        ``rows``: dicts with ``seller_sku`` and optional ``item_id``,
        ``sku_id``, ``quantity``, ``price`` (Request/Product/Skus/Sku).
        """
        request = ElementTree.Element("Request")
        skus = ElementTree.SubElement(
            ElementTree.SubElement(request, "Product"), "Skus"
        )
        for row in rows:
            sku = ElementTree.SubElement(skus, "Sku")
            if row.get("item_id"):
                ElementTree.SubElement(sku, "ItemId").text = str(row["item_id"])
            if row.get("sku_id"):
                ElementTree.SubElement(sku, "SkuId").text = str(row["sku_id"])
            ElementTree.SubElement(sku, "SellerSku").text = str(row["seller_sku"])
            if row.get("price") is not None:
                ElementTree.SubElement(sku, "Price").text = f"{float(row['price']):.2f}"
            if row.get("quantity") is not None:
                ElementTree.SubElement(sku, "Quantity").text = str(
                    int(max(row["quantity"], 0))
                )
        return ElementTree.tostring(request, encoding="unicode")

    def update_stock(self, access_token, seller_sku, sku_id, quantity,
                     item_id=None):
        """Push seller stock for one SKU to Lazada.

        ``ItemId``/``SkuId`` target the variant; ``SellerSku`` is always
        included so the SKU stays resolvable on Lazada's side.
        """
        return self.update_stock_batch(access_token, [{
            "seller_sku": seller_sku, "sku_id": sku_id, "item_id": item_id,
            "quantity": quantity,
        }])

    def update_stock_batch(self, access_token, stock_list):
        """Push stock for several SKUs in one call (Lazada accepts up to 50).

        ``stock_list``: dicts with ``seller_sku``, ``quantity`` and optional
        ``item_id``/``sku_id``.
        """
        rows = [dict(row, price=None) for row in stock_list]
        return self._post(
            "/product/price_quantity/update", access_token,
            params={"payload": self._price_quantity_payload(rows)},
        )

    def update_price(self, access_token, price_list):
        """Push the selling price of one or more SKUs in one call.

        ``price_list``: dicts with ``seller_sku``, ``price`` and optional
        ``item_id``/``sku_id``. Quantity is left unchanged.
        """
        rows = [dict(row, quantity=None) for row in price_list]
        return self._post(
            "/product/price_quantity/update", access_token,
            params={"payload": self._price_quantity_payload(rows)},
        )

    # ------------------------------------------------------------------
    # Fulfillment: pack -> ready to ship -> AWB
    # ------------------------------------------------------------------
    def pack_order(self, access_token, order_id, order_item_ids,
                   shipping_allocate_type="TFS"):
        """Pack order items into Lazada package(s).

        ``delivery_type`` must be ``dropship``; pickup vs drop-off follows
        the seller's warehouse setting in Seller Center, not this call.
        ``TFS`` = Lazada allocates the carrier (local sellers).
        """
        payload = {
            "pack_order_list": [{
                "order_id": _numeric(order_id),
                "order_item_list": [_numeric(i) for i in order_item_ids],
            }],
            "delivery_type": "dropship",
            "shipping_allocate_type": shipping_allocate_type,
        }
        # A timeout/5xx may occur AFTER Lazada packed the items.
        # Never replay this side effect automatically.
        return self._request(
            "POST", "/order/fulfill/pack", access_token,
            params={"packReq": json.dumps(payload)}, retries=1, raw=True,
        )

    def ready_to_ship(self, access_token, package_ids):
        payload = {"packages": [{"package_id": str(p)} for p in package_ids]}
        # Notifies the carrier; never replayed automatically.
        return self._request(
            "POST", "/order/package/rts", access_token,
            params={"readyToShipReq": json.dumps(payload)}, retries=1, raw=True,
        )

    def get_awb_document(self, access_token, package_ids, doc_type="PDF"):
        payload = {
            "doc_type": doc_type,
            "packages": [{"package_id": str(p)} for p in package_ids],
        }
        return self._request(
            "POST", "/order/package/document/get", access_token,
            params={"getDocumentReq": json.dumps(payload)}, raw=True,
        )

    def download_document(self, url):
        """Fetch the AWB PDF from the short-lived (10 min) URL Lazada returns."""
        parsed = urllib.parse.urlparse(str(url or ""))
        if parsed.scheme != "https" or not parsed.netloc:
            raise LazadaAPIError(
                "document_url", "Lazada did not return an HTTPS document URL."
            )
        # The query string usually carries a download signature - don't log it.
        endpoint = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        started = time.monotonic()
        try:
            resp = requests.get(url, timeout=60)
        except (requests.ConnectionError, requests.Timeout) as exc:
            error = LazadaAPIError("network", type(exc).__name__)
            self._write_log("GET", endpoint, {}, None, None, "error", 0,
                            started, error)
            raise error from exc
        content = resp.content or b""
        if (resp.status_code >= 400 or not content.startswith(b"%PDF-")
                or len(content) > _MAX_DOCUMENT_BYTES):
            error = LazadaAPIError(
                "document_not_pdf",
                "Lazada did not return a PDF label. Regenerate the label later.",
            )
            self._write_log("GET", endpoint, {}, None,
                            {"bytes": len(content)}, "error",
                            resp.status_code, started, error)
            raise error
        self._write_log("GET", endpoint, {}, None,
                        {"format": "pdf", "bytes": len(content)}, "success",
                        resp.status_code, started, None)
        return content
