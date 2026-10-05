import json
import logging
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

from .shopee_api import _mask_value

_logger = logging.getLogger(__name__)


class ShopeeApiLog(models.Model):
    _name = "shopee.api.log"
    _description = "Shopee API Log"
    _order = "create_date desc"

    name = fields.Char(required=True, index=True)
    shopee_config_id = fields.Many2one(
        "shopee.config", string="Shop", ondelete="set null", index=True
    )
    company_id = fields.Many2one(related="shopee_config_id.company_id", store=True, index=True)
    log_type = fields.Selection(
        [("request", "API Request"), ("webhook", "Webhook")],
        required=True,
        default="request",
    )
    status = fields.Selection(
        [("success", "Success"), ("error", "Error")],
        required=True,
        default="success",
    )
    http_method = fields.Selection(
        [("GET", "GET"), ("POST", "POST"), ("PUT", "PUT"), ("DELETE", "DELETE")]
    )
    endpoint = fields.Char()
    http_status = fields.Integer()
    duration_ms = fields.Integer()
    request_data = fields.Text()
    response_data = fields.Text()
    error_message = fields.Text()

    @api.model
    def create_api_log(self, config, **values):
        secrets = [config[field] for field in (
            "partner_key", "access_token", "refresh_token", "webhook_secret",
            "temp_auth_code", "temp_access_token", "temp_refresh_token", "oauth_state",
        ) if config and config[field]]

        def serialise(value):
            if value in (None, False):
                return False
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except ValueError:
                    pass
            value = _mask_value(value)
            result = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
            for secret in sorted(secrets, key=len, reverse=True):
                result = result.replace(secret, "***")
            return result

        values.update({
            "name": values.get("name") or values.get("endpoint") or "Shopee API",
            "shopee_config_id": config.id if config else False,
            "request_data": serialise(values.get("request_data")),
            "response_data": serialise(values.get("response_data")),
            "error_message": serialise(values.get("error_message")),
        })
        return self.create(values)


class ShopeeRetryQueue(models.Model):
    _name = "shopee.retry.queue"
    _description = "Shopee Sync Retry Queue"
    _order = "next_retry_at, id"
    _check_company_auto = True

    shopee_config_id = fields.Many2one(
        "shopee.config", required=True, ondelete="cascade", index=True, check_company=True
    )
    company_id = fields.Many2one(related="shopee_config_id.company_id", store=True, index=True)
    operation_type = fields.Selection(
        [
            ("sync_order", "Import Order"),
            ("sync_order_status", "Sync Order Status"),
            ("push_stock", "Push Product Stock"),
            ("push_price", "Push Product Price"),
            ("sync_stock", "Import Stock"),
        ],
        required=True,
    )
    payload = fields.Text(required=True)
    state = fields.Selection(
        [("pending", "Pending"), ("done", "Done"), ("failed", "Failed")],
        default="pending",
        required=True,
        index=True,
    )
    attempts = fields.Integer(default=0)
    max_attempts = fields.Integer(default=5)
    next_retry_at = fields.Datetime(default=fields.Datetime.now, index=True)
    last_attempt_at = fields.Datetime()
    error_message = fields.Text()

    @api.model
    def enqueue(self, config, operation_type, payload, error_message=None):
        return self.create({
            "shopee_config_id": config.id,
            "operation_type": operation_type,
            "payload": json.dumps(payload, ensure_ascii=False, default=str),
            "error_message": error_message or False,
        })

    def _run_one(self):
        self.ensure_one()
        self.check_access_rights("write")
        self.check_access_rule("write")
        self.flush_recordset()
        self.env.cr.execute(
            "SELECT id FROM shopee_retry_queue WHERE id = %s FOR UPDATE SKIP LOCKED",
            [self.id],
        )
        if not self.env.cr.fetchone():
            return
        self.invalidate_recordset()
        if (self.state != "pending" or not self.shopee_config_id.active
                or (self.next_retry_at and self.next_retry_at > fields.Datetime.now())):
            return
        config = self.shopee_config_id.with_company(self.company_id).with_context(
            allowed_company_ids=[self.company_id.id],
        )
        if self.attempts >= self.max_attempts:
            self.state = "failed"
            return
        self.write({
            "attempts": self.attempts + 1,
            "last_attempt_at": fields.Datetime.now(),
        })
        try:
            payload = json.loads(self.payload or "{}")
            if not isinstance(payload, dict):
                raise ValueError("Retry payload must be an object.")
            if self.operation_type in ("sync_order", "sync_order_status"):
                if not isinstance(payload.get("order_sn"), str) or not payload["order_sn"].strip():
                    raise ValueError("Retry payload requires an order_sn string.")
            if self.operation_type in ("push_stock", "push_price"):
                if type(payload.get("product_id")) is not int or payload["product_id"] <= 0:
                    raise ValueError("Retry payload requires a positive product_id.")
        except ValueError:
            self.write({"state": "failed", "error_message": "Invalid retry payload."})
            return
        try:
            with self.env.cr.savepoint():
                if self.operation_type == "sync_order":
                    config.import_order_by_sn(payload["order_sn"])
                elif self.operation_type == "sync_order_status":
                    config.sync_order_statuses([payload["order_sn"]])
                elif self.operation_type == "push_stock":
                    product = config.env["product.product"].browse(payload["product_id"]).exists()
                    if not product or (product.company_id and product.company_id != config.company_id):
                        raise UserError("Retry product is missing or belongs to another company.")
                    config._push_stock_for_products(product)
                elif self.operation_type == "push_price":
                    product = config.env["product.product"].browse(payload["product_id"]).exists()
                    if not product or (product.company_id and product.company_id != config.company_id):
                        raise UserError("Retry product is missing or belongs to another company.")
                    config._push_price_for_products(product)
                elif self.operation_type == "sync_stock":
                    config.action_sync_stock()
            self.write({"state": "done", "error_message": False})
        except Exception as exc:
            _logger.warning("Shopee retry failed for queue %s (%s)", self.id, type(exc).__name__)
            if self.attempts >= self.max_attempts:
                self.write({"state": "failed", "error_message": str(exc)})
            else:
                self.write({
                    "next_retry_at": fields.Datetime.now()
                    + timedelta(minutes=2 ** min(self.attempts, 6)),
                    "error_message": str(exc),
                })

    @api.model
    def cron_process(self):
        jobs = self.search([
            ("state", "=", "pending"),
            ("shopee_config_id.active", "=", True),
            ("next_retry_at", "<=", fields.Datetime.now()),
        ], limit=50)
        for job in jobs:
            job._run_one()
