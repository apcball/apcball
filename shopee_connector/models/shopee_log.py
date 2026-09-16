import json
import logging
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ShopeeApiLog(models.Model):
    _name = "shopee.api.log"
    _description = "Shopee API Log"
    _order = "create_date desc"

    name = fields.Char(required=True, index=True)
    shopee_config_id = fields.Many2one(
        "shopee.config", string="Shop", ondelete="set null", index=True
    )
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
        def serialise(value):
            if value in (None, False):
                return False
            if isinstance(value, str):
                return value
            return json.dumps(value, ensure_ascii=False, default=str)

        values.update({
            "name": values.get("name") or values.get("endpoint") or "Shopee API",
            "shopee_config_id": config.id if config else False,
            "request_data": serialise(values.get("request_data")),
            "response_data": serialise(values.get("response_data")),
        })
        return self.sudo().create(values)


class ShopeeRetryQueue(models.Model):
    _name = "shopee.retry.queue"
    _description = "Shopee Sync Retry Queue"
    _order = "next_retry_at, id"

    shopee_config_id = fields.Many2one(
        "shopee.config", required=True, ondelete="cascade", index=True
    )
    operation_type = fields.Selection(
        [
            ("sync_order", "Import Order"),
            ("sync_order_status", "Sync Order Status"),
            ("push_stock", "Push Product Stock"),
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
        config = self.shopee_config_id
        payload = json.loads(self.payload or "{}")
        self.write({
            "attempts": self.attempts + 1,
            "last_attempt_at": fields.Datetime.now(),
        })
        try:
            if self.operation_type == "sync_order":
                config.import_order_by_sn(payload["order_sn"])
            elif self.operation_type == "sync_order_status":
                config.sync_order_statuses([payload["order_sn"]])
            elif self.operation_type == "push_stock":
                product = self.env["product.product"].browse(payload["product_id"]).exists()
                config._push_stock_for_products(product)
            self.write({"state": "done", "error_message": False})
        except Exception as exc:
            _logger.exception("Shopee retry failed for queue %s", self.id)
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
            ("next_retry_at", "<=", fields.Datetime.now()),
        ], limit=50)
        for job in jobs:
            job._run_one()
