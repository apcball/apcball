import hashlib
import hmac
import json
import logging

import werkzeug
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class ShopeeCallbackController(http.Controller):
    @http.route(
        "/shopee/callback", type="http", auth="public", website=False, csrf=False
    )
    def shopee_callback(self, code=None, shop_id=None, state=None, **kwargs):
        Config = request.env["shopee.config"].sudo()
        domain = [("active", "=", True)]
        if state:
            domain.append(("oauth_state", "=", state))
        elif shop_id:
            domain.append(("shop_id", "=", str(shop_id)))
        configs = Config.search(domain)
        if len(configs) != 1 or not code:
            _logger.warning("Rejected Shopee OAuth callback for shop %s", shop_id)
            return request.make_response(
                "Invalid or expired Shopee authorization callback.",
                status=400,
                headers=[("Content-Type", "text/plain")],
            )
        config = configs[0]
        if config.shop_id and shop_id and str(config.shop_id) != str(shop_id):
            return request.make_response(
                "Shopee shop does not match the authorization request.",
                status=400,
                headers=[("Content-Type", "text/plain")],
            )
        config.write({"temp_auth_code": code, "shop_id": shop_id or config.shop_id})
        return werkzeug.utils.redirect(
            f"/web#id={config.id}&model=shopee.config&view_type=form", 302
        )


class ShopeeWebhookController(http.Controller):
    @staticmethod
    def _signature_valid(config, raw_body, signature):
        secret = config.webhook_secret or config.partner_key
        if not signature:
            return not config.webhook_secret
        expected = hmac.new(
            secret.encode(), raw_body, hashlib.sha256
        ).hexdigest()
        supplied = signature.split("=", 1)[-1].strip()
        return hmac.compare_digest(expected, supplied)

    @http.route(
        ["/shopee/webhook", "/shopee/webhook/<string:shop_id>"],
        type="http", auth="public", website=False, csrf=False,
        methods=["POST"],
    )
    def shopee_webhook(self, shop_id=None, **kwargs):
        raw_body = request.httprequest.get_data(cache=True) or b"{}"
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return request.make_json_response(
                {"ok": False, "error": "invalid_json"}, status=400
            )
        data = payload.get("data") or payload
        shop_id = shop_id or data.get("shop_id") or payload.get("shop_id")
        Config = request.env["shopee.config"].sudo()
        configs = Config.search([
            ("active", "=", True),
            ("shop_id", "=", str(shop_id)),
        ]) if shop_id else Config.search([("active", "=", True)])
        if len(configs) != 1:
            return request.make_json_response(
                {"ok": False, "error": "unknown_shop"}, status=404
            )
        config = configs[0]
        signature = (
            request.httprequest.headers.get("X-Shopee-Signature")
            or request.httprequest.headers.get("Authorization")
        )
        if not self._signature_valid(config, raw_body, signature):
            config._write_api_log(
                log_type="webhook", endpoint="/shopee/webhook",
                request_data=payload, response_data={"ok": False},
                status="error", error_message="Invalid webhook signature",
            )
            return request.make_json_response(
                {"ok": False, "error": "invalid_signature"}, status=401
            )
        try:
            result = config.process_webhook(payload)
            response = {"ok": True, "result": result}
            config._write_api_log(
                log_type="webhook", endpoint="/shopee/webhook",
                request_data=payload, response_data=response, status="success",
            )
            return request.make_json_response(response)
        except Exception as exc:
            _logger.exception("Shopee webhook processing failed")
            order_sn = data.get("ordersn") or data.get("order_sn")
            if order_sn:
                event = payload.get("event_type") or payload.get("code") or ""
                operation = (
                    "sync_order_status"
                    if "STATUS" in event.upper()
                    else "sync_order"
                )
                request.env["shopee.retry.queue"].sudo().enqueue(
                    config, operation, {"order_sn": order_sn}, str(exc)
                )
            config._write_api_log(
                log_type="webhook", endpoint="/shopee/webhook",
                request_data=payload, response_data={"ok": False},
                status="error", error_message=str(exc),
            )
            # A 200 response prevents Shopee from retrying indefinitely; the
            # durable retry queue handles transient Odoo/API failures.
            return request.make_json_response({"ok": True, "queued": True})
