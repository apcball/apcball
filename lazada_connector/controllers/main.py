import hashlib
import hmac
import json
import logging

import werkzeug
from odoo import fields, http
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
        if not code:
            configs = Config.browse()
        elif state:
            configs = Config.search([
                ("active", "=", True), ("oauth_state", "=", state),
            ], limit=2)
        else:
            # Lazada may not echo "state": only accept a single pending,
            # unexpired authorization started from Odoo.
            configs = Config.search([
                ("active", "=", True), ("oauth_state", "!=", False),
                ("oauth_state_expires_at", ">", fields.Datetime.now()),
            ], limit=2)
        if len(configs) != 1 or not configs._accept_oauth_callback(state, code):
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
        if not signature or not secret:
            return False
        base = str(config.app_key).encode() + raw_body
        expected = hmac.new(
            secret.encode(), base, hashlib.sha256
        ).hexdigest()
        supplied = signature.strip()
        if supplied.lower().startswith("bearer "):
            supplied = supplied[7:].strip()
        supplied = supplied.split("=", 1)[-1].strip().lower()
        return supplied.isascii() and hmac.compare_digest(expected, supplied)

    @staticmethod
    def _valid_order_id(order_id):
        return (
            isinstance(order_id, (str, int)) and not isinstance(order_id, bool)
            and bool(str(order_id).strip())
        )

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
        if not isinstance(payload, dict) or (
            "data" in payload and not isinstance(payload["data"], dict)
        ):
            return request.make_json_response(
                {"ok": False, "error": "invalid_payload"}, status=400
            )
        seller_ids = [value for value in (
            seller_id, payload.get("seller_id"), payload.get("SellerId"),
        ) if value is not None]
        if any(
            isinstance(value, (dict, list, bool)) or str(value) != str(seller_ids[0])
            for value in seller_ids
        ):
            return request.make_json_response(
                {"ok": False, "error": "invalid_seller"}, status=400
            )
        webhook_seller_id = seller_ids[0] if seller_ids else None
        Config = request.env["lazada.config"].sudo()
        active_configs = Config.search([("active", "=", True)])
        signature = (
            request.httprequest.headers.get("X-Lazada-Signature")
            or request.httprequest.headers.get("Authorization")
        )
        configs = active_configs.filtered(
            lambda item: item.seller_id == str(webhook_seller_id)
        ) if webhook_seller_id else active_configs
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
        config = configs[0].with_company(configs[0].company_id)
        if not self._signature_valid(config, raw_body, signature):
            config._write_api_log(
                log_type="webhook", endpoint="/lazada/webhook",
                request_data=payload, response_data={"ok": False},
                status="error", error_message="Invalid webhook signature",
            )
            return request.make_json_response(
                {"ok": False, "error": "invalid_signature"}, status=401
            )
        operation = config._webhook_operation(payload)
        order_id = config._webhook_order_id(payload)
        if operation == "sync_order" and not self._valid_order_id(order_id):
            return request.make_json_response(
                {"ok": False, "error": "invalid_order"}, status=400
            )
        try:
            with request.env.cr.savepoint():
                result = config.process_webhook(payload)
            response = {"ok": True, "result": result}
            config._write_api_log(
                log_type="webhook", endpoint="/lazada/webhook",
                request_data=payload, response_data=response, status="success",
            )
            return request.make_json_response(response)
        except Exception as exc:
            _logger.warning("Lazada webhook processing failed for config %s", config.id)
            queued = False
            if operation == "sync_stock" or (operation == "sync_order" and order_id):
                try:
                    with request.env.cr.savepoint():
                        request.env["lazada.retry.queue"].sudo().enqueue(
                            config, operation,
                            {"order_id": str(order_id).strip()} if operation == "sync_order" else {},
                            str(exc),
                        )
                    queued = True
                except Exception:
                    _logger.warning("Unable to queue Lazada webhook for config %s", config.id)
            config._write_api_log(
                log_type="webhook", endpoint="/lazada/webhook",
                request_data=payload, response_data={"ok": False},
                status="error", error_message=str(exc),
            )
            # A 200 response prevents Lazada from retrying indefinitely; the
            # durable retry queue handles transient Odoo/API failures. Without
            # a queued retry, ask Lazada to send the event again.
            return request.make_json_response(
                {"ok": queued, "queued": queued}, status=200 if queued else 503
            )
