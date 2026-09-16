import hashlib
import hmac
import json
import logging
import time
import urllib.parse

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

_MASK_KEYS = ("app_secret", "access_token", "sign", "refresh_token", "code")
_MAX_LIST = 50


class LazadaAPIError(Exception):
    """Raised when Lazada returns a non-zero ``code`` field."""

    def __init__(self, error, message="", request_id=""):
        self.error = error
        self.message = message
        self.request_id = request_id
        super().__init__(
            f"Lazada API error [{error}]: {message or '(no message)'}"
            + (f" (request_id={request_id})" if request_id else "")
        )


def _mask(params):
    return {
        k: ("***" if k in _MASK_KEYS and v else v)
        for k, v in (params or {}).items()
    }


def _mask_value(value):
    if isinstance(value, dict):
        return {
            key: ("***" if key in _MASK_KEYS and item else _mask_value(item))
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
                 is_public=False):
        """Single entry point for every Lazada call.

        Lazada keeps every parameter (including POST payloads) in the query
        string and signs them all together. Common params: app_key,
        timestamp (ms), sign_method, access_token (user calls), sign.
        Retries 3x on connection errors / 5xx; never retries a 4xx or a
        Lazada business error.
        """
        query = {
            "app_key": self.app_key,
            "sign_method": "sha256",
            "timestamp": int(time.time() * 1000),
        }
        if not is_public and access_token:
            query["access_token"] = access_token
        if params:
            query.update(params)
        query["sign"] = self._sign(path, query)

        # Token creation/refresh always live on the auth host, regardless
        # of region - every other endpoint uses the regional API host.
        base = AUTH_REST_BASE if path.startswith("/auth/") else self.host
        url = f"{base}{path}"
        _logger.debug("Lazada %s %s params=%s", method, path, _mask(query))

        started = time.monotonic()
        delay = 0.5
        last_exc = None
        for attempt in range(3):
            try:
                resp = requests.request(method, url, params=query, timeout=30)
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_exc = exc
                _logger.warning("Lazada %s %s network error (try %s): %s",
                                method, path, attempt + 1, exc)
                time.sleep(delay)
                delay *= 2
                continue

            if resp.status_code >= 500:
                last_exc = requests.HTTPError(f"HTTP {resp.status_code}", response=resp)
                _logger.warning("Lazada %s %s HTTP %s (try %s)",
                                method, path, resp.status_code, attempt + 1)
                time.sleep(delay)
                delay *= 2
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
                    method, path, query, data or resp.text[:500],
                    "error", resp.status_code, started, exc,
                )
                raise exc
            if data is None:
                exc = LazadaAPIError("non_json_response", resp.text[:500])
                self._write_log(
                    method, path, query, resp.text[:500],
                    "error", resp.status_code, started, exc,
                )
                raise exc

            code = str(data.get("code", "0"))
            if code not in ("0", 0):
                exc = LazadaAPIError(
                    code,
                    data.get("message", ""),
                    data.get("request_id", ""),
                )
                self._write_log(
                    method, path, query, data, "error",
                    resp.status_code, started, exc,
                )
                raise exc
            self._write_log(
                method, path, query, data, "success",
                resp.status_code, started, None,
            )
            # OAuth responses put tokens at the top level; business APIs
            # normally wrap their payload in "data".
            if path in ("/auth/token/create", "/auth/token/refresh"):
                return data
            return data.get("data") or {}

        exc = LazadaAPIError("network", f"{last_exc}")
        self._write_log(
            method, path, query, None, "error", 0, started, exc,
        )
        raise exc

    def _write_log(
        self, method, path, params, response, status,
        http_status, started, error,
    ):
        if not self.log_callback:
            return
        try:
            self.log_callback(
                http_method=method,
                endpoint=path,
                request_data={"params": _mask(params)},
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
        params = {
            "created_after": int(created_after),
            "offset": int(offset),
            "limit": int(limit),
            "sort_by": "created_at",
            "sort_direction": "DESC",
        }
        if created_before:
            params["created_before"] = int(created_before)
        return self._get("/orders/get", access_token, params)

    def get_order(self, access_token, order_id):
        return self._get(
            "/order/get", access_token, {"order_id": str(order_id)}
        )

    def get_order_items(self, access_token, order_id):
        return self._get(
            "/order/items/get", access_token, {"order_id": str(order_id)}
        )

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

    def update_stock(self, access_token, seller_sku, sku_id, quantity):
        """Push seller stock for one SKU to Lazada.

        ``product/price_quantity/update`` expects a JSON ``payload`` query
        parameter. ``SkuId`` targets a product variant; ``SellerSku`` is
        always included so the SKU stays resolvable on Lazada's side.
        """
        entry = {"SellerSku": str(seller_sku)}
        if sku_id:
            entry["SkuId"] = int(sku_id)
        entry["Quantity"] = int(max(quantity, 0))
        return self._post(
            "/product/price_quantity/update", access_token,
            params={"payload": json.dumps([entry])},
        )
