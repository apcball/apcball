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
        configs = Config.search([
            ("active", "=", True), ("oauth_state", "=", state),
        ], limit=2) if state and code else Config.browse()
        if len(configs) != 1 or not configs._accept_oauth_callback(state, code, shop_id):
            _logger.warning("Rejected Shopee OAuth callback")
            return request.make_response(
                "Invalid or expired Shopee authorization callback.",
                status=400,
                headers=[("Content-Type", "text/plain")],
            )
        config = configs[0]
        return werkzeug.utils.redirect(
            f"/web#id={config.id}&model=shopee.config&view_type=form", 302
        )


class ShopeeWebhookController(http.Controller):
    @staticmethod
    def _signature_valid(config, raw_body, signature):
        secret = config.webhook_secret or config.partner_key
        if not signature or not secret:
            return False
        expected = hmac.new(
            secret.encode(), raw_body, hashlib.sha256
        ).hexdigest()
        supplied = signature.split("=", 1)[-1].strip()
        return supplied.isascii() and hmac.compare_digest(expected, supplied)

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
        if not isinstance(payload, dict) or (
            "data" in payload and not isinstance(payload["data"], dict)
        ):
            return request.make_json_response(
                {"ok": False, "error": "invalid_payload"}, status=400
            )
        data = payload.get("data", payload)
        shop_ids = [value for value in (
            shop_id, data.get("shop_id"), payload.get("shop_id"),
        ) if value is not None]
        if not shop_ids or any(
            isinstance(value, (dict, list, bool)) or str(value) != str(shop_ids[0])
            for value in shop_ids
        ):
            return request.make_json_response(
                {"ok": False, "error": "invalid_shop"}, status=400
            )
        shop_id = shop_ids[0]
        Config = request.env["shopee.config"].sudo()
        configs = Config.search([
            ("active", "=", True),
            ("shop_id", "=", str(shop_id)),
        ], limit=2)
        if len(configs) != 1:
            return request.make_json_response(
                {"ok": False, "error": "unknown_shop"}, status=404
            )
        config = configs[0].with_company(configs[0].company_id)
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
        operation = config._webhook_operation(payload)
        order_sn = data.get("ordersn") or data.get("order_sn")
        if operation in ("sync_order", "sync_order_status") and (
            not isinstance(order_sn, str) or not order_sn.strip()
        ):
            return request.make_json_response(
                {"ok": False, "error": "invalid_order"}, status=400
            )
        try:
            with request.env.cr.savepoint():
                result = config.process_webhook(payload)
            response = {"ok": True, "result": result}
            config._write_api_log(
                log_type="webhook", endpoint="/shopee/webhook",
                request_data=payload, response_data=response, status="success",
            )
            return request.make_json_response(response)
        except Exception as exc:
            _logger.warning("Shopee webhook processing failed for config %s", config.id)
            queued = False
            if operation and (order_sn or operation == "sync_stock"):
                try:
                    with request.env.cr.savepoint():
                        request.env["shopee.retry.queue"].sudo().enqueue(
                            config, operation,
                            {"order_sn": order_sn} if order_sn else {}, str(exc),
                        )
                    queued = True
                except Exception:
                    _logger.warning("Unable to queue Shopee webhook for config %s", config.id)
            config._write_api_log(
                log_type="webhook", endpoint="/shopee/webhook",
                request_data=payload, response_data={"ok": False},
                status="error", error_message=str(exc),
            )
            # A 200 response prevents Shopee from retrying indefinitely; the
            # durable retry queue handles transient Odoo/API failures.
            return request.make_json_response(
                {"ok": queued, "queued": queued}, status=200 if queued else 503
            )
