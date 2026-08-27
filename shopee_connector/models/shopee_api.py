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

_MASK_KEYS = ("partner_key", "access_token", "sign", "refresh_token", "code")
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
    return {
        k: ("***" if k in _MASK_KEYS and v else v)
        for k, v in (params or {}).items()
    }


class ShopeeAPI:
    """Thin wrapper around Shopee Open Platform v2 REST API.
    Not an Odoo model - instantiate from a shopee.config record.
    """

    def __init__(self, partner_id, partner_key, shop_id=None, environment="sandbox"):
        self.partner_id = str(partner_id).strip()
        self.partner_key = str(partner_key).strip()
        self.shop_id = str(shop_id).strip() if shop_id else None
        self.host = SANDBOX_HOST if environment == "sandbox" else PRODUCTION_HOST

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
                 is_public=False):
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

        delay = 0.5
        last_exc = None
        for attempt in range(3):
            try:
                resp = requests.request(
                    method, url, params=query, json=body if method == "POST" else None,
                    timeout=30,
                )
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_exc = exc
                _logger.warning("Shopee %s %s network error (try %s): %s",
                                method, path, attempt + 1, exc)
                time.sleep(delay)
                delay *= 2
                continue

            if resp.status_code >= 500:
                last_exc = requests.HTTPError(f"HTTP {resp.status_code}", response=resp)
                _logger.warning("Shopee %s %s HTTP %s (try %s)",
                                method, path, resp.status_code, attempt + 1)
                time.sleep(delay)
                delay *= 2
                continue

            try:
                data = resp.json()
            except ValueError:
                resp.raise_for_status()
                raise ShopeeAPIError("non_json_response", resp.text[:500])

            if data.get("error"):
                raise ShopeeAPIError(
                    data.get("error"),
                    data.get("message", ""),
                    data.get("request_id", ""),
                )
            if data.get("warning"):
                _logger.warning("Shopee %s warning: %s", path, data["warning"])
            return data

        raise ShopeeAPIError("network", f"{last_exc}")

    def _get(self, path, access_token, params=None):
        return self._request("GET", path, access_token, params=params)

    def _post(self, path, access_token, body=None, is_public=False):
        return self._request(
            "POST", path, access_token, body=body or {}, is_public=is_public
        )

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------
    def get_authorization_url(self, redirect_url):
        path = "/api/v2/shop/auth_partner"
        timestamp = int(time.time())
        signature = self._sign(path, timestamp)
        redirect = urllib.parse.quote(redirect_url, safe="")
        return (
            f"{self.host}{path}?partner_id={self.partner_id}"
            f"&timestamp={timestamp}&sign={signature}&redirect={redirect}"
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
                "shipping_carrier,payment_method,order_status"
            ),
        }
        return self._get(path, access_token, params)

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

    def update_stock(self, access_token, item_id, model_id, quantity):
        """Push seller stock for one item (optionally one model) to Shopee.

        Shopee v2 ``update_stock`` expects ``seller_stock`` under each entry of
        ``stock_list``. ``model_id`` 0 / omitted targets an item with no models.
        """
        path = "/api/v2/product/update_stock"
        entry = {}
        if model_id:
            entry["model_id"] = int(model_id)
        entry["seller_stock"] = [{"stock": int(max(quantity, 0))}]
        body = {"item_id": int(item_id), "stock_list": [entry]}
        return self._post(path, access_token, body=body)
