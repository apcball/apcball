import hashlib
import hmac
import logging
import time
import urllib.parse

import requests

_logger = logging.getLogger(__name__)

# Sandbox v2 lives on the shopee.sg open-platform host, not the classic
# partner.test-stable.shopeemobile.com endpoint.
SANDBOX_HOST = "https://openplatform.sandbox.test-stable.shopee.sg"
PRODUCTION_HOST = "https://partner.shopeemobile.com"

_MASK_KEYS = ("partner_key", "access_token", "sign", "refresh_token", "code",
              "webhook_secret", "authorization", "oauth_state", "temp_auth_code",
              "temp_access_token", "temp_refresh_token")
_MAX_LIST = 50


class ShopeeAPIError(Exception):
    """Raised when Shopee returns a non-empty ``error`` field."""

    def __init__(self, error, message="", request_id=""):
        self.error = error
        self.message = message
        self.request_id = request_id
        super().__init__(
            f"Shopee API error [{error}]: {message or '(no message)'}"
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


class ShopeeAPI:
    """Thin wrapper around Shopee Open Platform v2 REST API.
    Not an Odoo model - instantiate from a shopee.config record.
    """

    def __init__(
        self, partner_id, partner_key, shop_id=None, environment="sandbox",
        log_callback=None,
    ):
        self.partner_id = str(partner_id).strip()
        self.partner_key = str(partner_key).strip()
        self.shop_id = str(shop_id).strip() if shop_id else None
        self.host = SANDBOX_HOST if environment == "sandbox" else PRODUCTION_HOST
        self.log_callback = log_callback

    # ------------------------------------------------------------------
    # Signing
    # ------------------------------------------------------------------
    def _sign(self, path, timestamp, access_token="", shop_id=None):
        """Shopee v2 signature.

        Public APIs (auth/token/*):
            base = partner_id + path + timestamp
        Shop APIs:
            base = partner_id + path + timestamp + access_token + shop_id
        """
        base = f"{self.partner_id}{path}{timestamp}"
        if access_token and shop_id:
            base += f"{access_token}{shop_id}"
        return hmac.new(
            self.partner_key.encode(), base.encode(), hashlib.sha256
        ).hexdigest()

    # ------------------------------------------------------------------
    # Core request
    # ------------------------------------------------------------------
    def _request(self, method, path, access_token="", params=None, body=None,
                 is_public=False, retries=3, binary=False):
        """Single entry point for every Shopee call.

        * Public (auth/token) calls: sign with partner_id+path+timestamp only,
          and keep shop_id/partner_id in the JSON body, not the query string.
        * Shop calls: sign with access_token+shop_id and put the common params
          in the query string.
        Retries 3x on connection errors / 5xx; never retries a 4xx or a Shopee
        business error.
        """
        timestamp = int(time.time())
        query = {
            "partner_id": self.partner_id,
            "timestamp": timestamp,
        }
        if is_public:
            query["sign"] = self._sign(path, timestamp)
        else:
            query["sign"] = self._sign(
                path, timestamp, access_token, self.shop_id
            )
            if access_token:
                query["access_token"] = access_token
            if self.shop_id:
                query["shop_id"] = self.shop_id
        if params:
            query.update(params)

        url = f"{self.host}{path}"
        _logger.debug("Shopee %s %s params=%s body=%s",
                      method, path, _mask(query), _mask(body))

        started = time.monotonic()
        delay = 0.5
        last_exc = None
        for attempt in range(retries):
            try:
                resp = requests.request(
                    method, url, params=query, json=body if method == "POST" else None,
                    timeout=30,
                )
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_exc = exc
                _logger.warning("Shopee %s %s network error (try %s): %s",
                                method, path, attempt + 1, type(exc).__name__)
                if attempt + 1 < retries:
                    time.sleep(delay)
                delay *= 2
                continue

            if resp.status_code >= 500:
                last_exc = requests.HTTPError(f"HTTP {resp.status_code}", response=resp)
                _logger.warning("Shopee %s %s HTTP %s (try %s)",
                                method, path, resp.status_code, attempt + 1)
                if attempt + 1 < retries:
                    time.sleep(delay)
                delay *= 2
                continue

            if binary and resp.status_code < 400 and resp.content.startswith(b"%PDF-"):
                self._write_log(
                    method, path, query, body,
                    {"format": "pdf", "bytes": len(resp.content)},
                    "success", resp.status_code, started, None,
                )
                return resp.content

            try:
                data = resp.json()
            except ValueError:
                data = None
            if resp.status_code >= 400:
                message = (data or {}).get("message") if isinstance(data, dict) else resp.text[:500]
                error = (data or {}).get("error") if isinstance(data, dict) else None
                exc = ShopeeAPIError(error or f"http_{resp.status_code}", message or "")
                self._write_log(
                    method, path, query, body, data or resp.text[:500],
                    "error", resp.status_code, started, exc,
                )
                raise exc
            if data is None:
                exc = ShopeeAPIError("non_json_response", resp.text[:500])
                self._write_log(
                    method, path, query, body, resp.text[:500],
                    "error", resp.status_code, started, exc,
                )
                raise exc

            if not isinstance(data, dict):
                raise ShopeeAPIError("invalid_response", "Expected a JSON object.")
            if data.get("error"):
                exc = ShopeeAPIError(
                    data.get("error"),
                    data.get("message", ""),
                    data.get("request_id", ""),
                )
                self._write_log(
                    method, path, query, body, data, "error",
                    resp.status_code, started, exc,
                )
                raise exc
            if binary:
                raise ShopeeAPIError("document_not_pdf", "Shopee did not return a PDF. Try checking the document status again.")
            if data.get("warning"):
                _logger.warning("Shopee %s warning: %s", path, data["warning"])
            self._write_log(
                method, path, query, body, data, "success",
                resp.status_code, started, None,
            )
            return data

        exc = ShopeeAPIError("network", type(last_exc).__name__)
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
            self.log_callback(
                http_method=method,
                endpoint=path,
                request_data={"params": _mask(params), "body": _mask(body or {})},
                response_data=_mask_value(response),
                status=status,
                http_status=http_status,
                duration_ms=int((time.monotonic() - started) * 1000),
                error_message=str(error) if error else False,
            )
        except Exception:
            _logger.exception("Unable to write Shopee API log")

    def _get(self, path, access_token, params=None):
        return self._request("GET", path, access_token, params=params)

    def _post(self, path, access_token, body=None, is_public=False):
        return self._request(
            "POST", path, access_token, body=body or {}, is_public=is_public
        )

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------
    def get_authorization_url(self, redirect_url, state=None):
        path = "/api/v2/shop/auth_partner"
        timestamp = int(time.time())
        signature = self._sign(path, timestamp)
        if state:
            parts = urllib.parse.urlsplit(redirect_url)
            query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
            query = [(key, value) for key, value in query if key != "state"]
            query.append(("state", str(state)))
            redirect_url = urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))
        redirect = urllib.parse.quote(redirect_url, safe="")
        return (
            f"{self.host}{path}?partner_id={self.partner_id}"
            f"&timestamp={timestamp}&sign={signature}&redirect={redirect}"
            + (f"&state={urllib.parse.quote(str(state), safe='')}" if state else "")
        )

    def get_access_token(self, code, shop_id):
        path = "/api/v2/auth/token/get"
        body = {"code": code, "shop_id": int(shop_id), "partner_id": int(self.partner_id)}
        return self._post(path, access_token="", body=body, is_public=True)

    def refresh_access_token(self, refresh_token, shop_id):
        path = "/api/v2/auth/access_token/get"
        body = {
            "refresh_token": refresh_token,
            "shop_id": int(shop_id),
            "partner_id": int(self.partner_id),
        }
        return self._post(path, access_token="", body=body, is_public=True)

    # ------------------------------------------------------------------
    # Shop
    # ------------------------------------------------------------------
    def get_shop_info(self, access_token):
        path = "/api/v2/shop/get_shop_info"
        return self._get(path, access_token)

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------
    def get_order_list(self, access_token, time_from, time_to, cursor=""):
        path = "/api/v2/order/get_order_list"
        params = {
            "time_range_field": "create_time",
            "time_from": time_from,
            "time_to": time_to,
            "page_size": 50,
            "cursor": cursor,
            "response_optional_fields": "order_status",
        }
        return self._get(path, access_token, params)

    def get_order_detail(self, access_token, order_sn_list):
        path = "/api/v2/order/get_order_detail"
        params = {
            "order_sn_list": ",".join(order_sn_list[:_MAX_LIST]),
            "response_optional_fields": (
                "buyer_username,item_list,total_amount,recipient_address,"
                "shipping_carrier,payment_method,order_status,package_list,"
                "pay_time"
            ),
        }
        return self._get(path, access_token, params)

    def get_escrow_detail(self, access_token, order_sn):
        """Income breakdown (shipping, vouchers, fees) of one order."""
        return self._get("/api/v2/payment/get_escrow_detail", access_token,
                         {"order_sn": order_sn})

    def get_order_status(self, access_token, order_sn_list):
        """Return current order details, including the status field."""
        return self.get_order_detail(access_token, order_sn_list)

    def ship_order(self, access_token, order_sn, package_number=None,
                   pickup=None, dropoff=None):
        path = "/api/v2/logistics/ship_order"
        body = {"order_sn": order_sn}
        if package_number:
            body["package_number"] = package_number
        if (pickup is None) == (dropoff is None):
            raise ShopeeAPIError("shipping_method", "Choose exactly one pickup or dropoff method.")
        body["pickup" if pickup is not None else "dropoff"] = pickup if pickup is not None else dropoff
        # A timeout/5xx may occur AFTER Shopee accepted the shipment.
        # Never replay this side effect automatically.
        return self._request("POST", path, access_token, body=body, retries=1)

    def get_shipping_parameter(self, access_token, order_sn):
        return self._get("/api/v2/logistics/get_shipping_parameter", access_token,
                         {"order_sn": order_sn})

    def get_tracking_number(self, access_token, order_sn, package_number=None):
        params = {"order_sn": order_sn}
        if package_number:
            params["package_number"] = package_number
        return self._get("/api/v2/logistics/get_tracking_number", access_token, params)

    def get_shipping_document_parameter(self, access_token, order):
        return self._post("/api/v2/logistics/get_shipping_document_parameter",
                          access_token, {"order_list": [order]})

    def create_shipping_document(self, access_token, order):
        return self._request("POST", "/api/v2/logistics/create_shipping_document",
                             access_token, body={"order_list": [order]}, retries=1)

    def get_shipping_document_result(self, access_token, order):
        return self._post("/api/v2/logistics/get_shipping_document_result",
                          access_token, {"order_list": [order]})

    def download_shipping_document(self, access_token, order, document_type):
        return self._request("POST", "/api/v2/logistics/download_shipping_document",
                             access_token, body={"shipping_document_type": document_type,
                                                 "order_list": [order]},
                             binary=True)

    def cancel_order(self, access_token, order_sn, cancel_reason="OTHER"):
        path = "/api/v2/order/cancel_order"
        return self._post(
            path, access_token,
            body={"order_sn": order_sn, "cancel_reason": cancel_reason},
        )

    # ------------------------------------------------------------------
    # Products / Stock
    # ------------------------------------------------------------------
    def get_item_list(self, access_token, offset=0, page_size=50):
        path = "/api/v2/product/get_item_list"
        params = {
            "offset": offset,
            "page_size": page_size,
            "item_status": "NORMAL",
        }
        return self._get(path, access_token, params)

    def get_item_base_info(self, access_token, item_id_list):
        path = "/api/v2/product/get_item_base_info"
        params = {
            "item_id_list": ",".join(
                str(i) for i in list(item_id_list)[:_MAX_LIST]
            ),
            "response_optional_fields": "item_sku,stock_info_v2,has_model",
        }
        return self._get(path, access_token, params)

    def get_model_list(self, access_token, item_id):
        path = "/api/v2/product/get_model_list"
        params = {
            "item_id": item_id,
            "response_optional_fields": "stock_info_v2",
        }
        return self._get(path, access_token, params)

    def update_stock(self, access_token, item_id, model_id, quantity,
                     location_id=None):
        """Push seller stock for one item (optionally one model) to Shopee.

        Shopee v2 ``update_stock`` expects ``seller_stock`` under each entry of
        ``stock_list``. ``model_id`` 0 / omitted targets an item with no models.
        ``location_id`` (e.g. "SGZ") is required by shops that keep stock per
        warehouse location; pass the one reported by ``get_model_list``.
        """
        path = "/api/v2/product/update_stock"
        entry = {}
        if model_id:
            entry["model_id"] = int(model_id)
        seller_stock = {"stock": int(max(quantity, 0))}
        if location_id:
            seller_stock["location_id"] = str(location_id)
        entry["seller_stock"] = [seller_stock]
        body = {"item_id": int(item_id), "stock_list": [entry]}
        return self._post(path, access_token, body=body)

    def update_stock_batch(self, access_token, item_id, stock_list):
        """Push seller stock for several models of one item in one call.

        ``stock_list``: iterable of ``{"model_id", "quantity", "location_id"}``
        (``location_id`` optional). One item's models must be sent together -
        Shopee's ``update_stock`` takes one ``item_id`` per request.
        """
        path = "/api/v2/product/update_stock"
        entries = []
        for row in stock_list:
            entry = {}
            if row.get("model_id"):
                entry["model_id"] = int(row["model_id"])
            seller_stock = {"stock": int(max(row["quantity"], 0))}
            if row.get("location_id"):
                seller_stock["location_id"] = str(row["location_id"])
            entry["seller_stock"] = [seller_stock]
            entries.append(entry)
        body = {"item_id": int(item_id), "stock_list": entries}
        return self._post(path, access_token, body=body)

    def update_price(self, access_token, item_id, price_list):
        """Push seller price for one or more models of an item in one call.

        ``price_list``: iterable of ``{"model_id", "original_price"}``.
        ``model_id`` 0 / omitted targets an item with no models.
        """
        path = "/api/v2/product/update_price"
        entries = []
        for row in price_list:
            entry = {"original_price": float(row["original_price"])}
            if row.get("model_id"):
                entry["model_id"] = int(row["model_id"])
            entries.append(entry)
        body = {"item_id": int(item_id), "price_list": entries}
        return self._post(path, access_token, body=body)
