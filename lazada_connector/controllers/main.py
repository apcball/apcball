import hashlib
import hmac
import json
import logging

import werkzeug
from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

from ..models.lazada_api import LazadaAPIError

_logger = logging.getLogger(__name__)


class LazadaCallbackController(http.Controller):
    @http.route(
        "/lazada/callback", type="http", auth="public", website=False, csrf=False
    )
    def lazada_callback(self, code=None, state=None, **kwargs):
        Config = request.env["lazada.config"].sudo()
        domain = [("active", "=", True)]
        if state:
            domain.append(("oauth_state", "=", state))
        configs = Config.search(domain)
        if len(configs) != 1 or not code:
            _logger.warning("Rejected Lazada OAuth callback")
            return request.make_response(
                "Invalid or expired Lazada authorization callback.",
                status=400,
                headers=[("Content-Type", "text/plain")],
            )
        config = configs[0]
        try:
            config._complete_authorization(code)
        except (LazadaAPIError, UserError):
            _logger.warning(
                "Lazada OAuth token exchange failed for config %s",
                config.id,
                exc_info=True,
            )
            return request.make_response(
                "Lazada authorization could not be completed. Start a new "
                "authorization from Odoo and try again.",
                status=400,
                headers=[("Content-Type", "text/plain")],
            )
        return werkzeug.utils.redirect(
            f"/web#id={config.id}&model=lazada.config&view_type=form", 302
        )


class LazadaWebhookController(http.Controller):
    @staticmethod
    def _signature_valid(config, raw_body, signature):
        secret = config.webhook_secret or config.app_secret
        if not signature:
            return False
        base = str(config.app_key).encode() + raw_body
        expected = hmac.new(
            secret.encode(), base, hashlib.sha256
        ).hexdigest()
        supplied = signature.strip()
        if supplied.lower().startswith("bearer "):
            supplied = supplied[7:].strip()
        supplied = supplied.split("=", 1)[-1].strip()
        return hmac.compare_digest(expected, supplied)

    @http.route(
        ["/lazada/webhook", "/lazada/webhook/<string:seller_id>"],
        type="http", auth="public", website=False, csrf=False,
        methods=["POST"],
    )
    def lazada_webhook(self, seller_id=None, **kwargs):
        raw_body = request.httprequest.get_data(cache=True) or b"{}"
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return request.make_json_response(
                {"ok": False, "error": "invalid_json"}, status=400
            )
        webhook_seller_id = (
            seller_id or payload.get("seller_id") or payload.get("SellerId")
        )
        Config = request.env["lazada.config"].sudo()
        active_configs = Config.search([("active", "=", True)])
        signature = (
            request.httprequest.headers.get("X-Lazada-Signature")
            or request.httprequest.headers.get("Authorization")
        )
        configs = Config.search([
            ("active", "=", True),
            ("seller_id", "=", str(webhook_seller_id)),
        ]) if webhook_seller_id else active_configs
        # Lazada's verification payload can carry a test seller id. Only use
        # a different connection when its configured secret validates the
        # supplied signature, never merely because it is the sole connection.
        if len(configs) != 1 and signature:
            configs = active_configs.filtered(
                lambda item: self._signature_valid(item, raw_body, signature)
            )
        if len(configs) != 1:
            return request.make_json_response(
                {"ok": False, "error": "unknown_seller"}, status=404
            )
        config = configs[0]
        if not self._signature_valid(config, raw_body, signature):
            config._write_api_log(
                log_type="webhook", endpoint="/lazada/webhook",
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
                log_type="webhook", endpoint="/lazada/webhook",
                request_data=payload, response_data=response, status="success",
            )
            return request.make_json_response(response)
        except Exception as exc:
            _logger.exception("Lazada webhook processing failed")
            data = payload.get("data") or payload
            message = data.get("message")
            if isinstance(message, str):
                try:
                    data = json.loads(message)
                except ValueError:
                    data = {}
            order_id = (
                data.get("order_id") if isinstance(data, dict) else None
            ) or payload.get("order_id")
            if order_id:
                event = str(
                    payload.get("event_type") or payload.get("type") or ""
                ).upper()
                operation = (
                    "sync_order_status"
                    if "STATUS" in event
                    else "sync_order"
                )
                request.env["lazada.retry.queue"].sudo().enqueue(
                    config, operation, {"order_id": str(order_id)}, str(exc)
                )
            config._write_api_log(
                log_type="webhook", endpoint="/lazada/webhook",
                request_data=payload, response_data={"ok": False},
                status="error", error_message=str(exc),
            )
            # A 200 response prevents Lazada from retrying indefinitely; the
            # durable retry queue handles transient Odoo/API failures.
            return request.make_json_response({"ok": True, "queued": True})
