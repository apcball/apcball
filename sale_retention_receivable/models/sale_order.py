from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    retention_enabled = fields.Boolean(
        string="Retention",
        compute="_compute_retention_enabled",
        store=True,
        readonly=False,
        help="Apply retention on this sale order.",
    )
    retention_percent = fields.Float(
        string="Retention (%)",
        compute="_compute_retention_settings",
        store=True,
        readonly=False,
    )
    retention_days = fields.Integer(
        string="Retention Days",
        compute="_compute_retention_settings",
        store=True,
        readonly=False,
    )
    retention_amount = fields.Monetary(
        string="Retention Amount",
        compute="_compute_retention_amount",
        store=True,
        currency_field="currency_id",
    )
    retention_due_date = fields.Date(
        string="Retention Due Date",
        compute="_compute_retention_due_date",
        store=True,
    )

    @api.depends("partner_id")
    def _compute_retention_enabled(self):
        for order in self:
            if order.partner_id:
                order.retention_enabled = order.partner_id.sale_retention_enabled
            else:
                order.retention_enabled = False

    @api.depends("partner_id", "retention_enabled")
    def _compute_retention_settings(self):
        ICP = self.env["ir.config_parameter"].sudo()
        for order in self:
            if order.retention_enabled and order.partner_id:
                order.retention_percent = order.partner_id.sale_retention_percent or float(
                    ICP.get_param("sale_retention_receivable.default_percent", "0.0")
                )
                order.retention_days = order.partner_id.sale_retention_days or int(
                    ICP.get_param("sale_retention_receivable.default_days", "0")
                )
            elif not order.retention_enabled:
                order.retention_percent = 0.0
                order.retention_days = 0

    @api.depends("order_line", "retention_percent", "retention_enabled")
    def _compute_retention_amount(self):
        for order in self:
            if order.retention_enabled and order.retention_percent:
                untaxed = order.amount_untaxed
                order.retention_amount = untaxed * (order.retention_percent / 100.0)
            else:
                order.retention_amount = 0.0

    @api.depends("date_order", "retention_days")
    def _compute_retention_due_date(self):
        for order in self:
            if order.retention_days and order.date_order:
                order.retention_due_date = fields.Date.add(
                    order.date_order, days=order.retention_days
                )
            else:
                order.retention_due_date = False

    @api.constrains("retention_percent")
    def _check_retention_percent(self):
        for order in self:
            if order.retention_enabled and order.retention_percent:
                if order.retention_percent < 0.0 or order.retention_percent > 100.0:
                    raise UserError(
                        _("Retention percentage must be between 0 and 100.")
                    )