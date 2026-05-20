from odoo import api, fields, models
from odoo.exceptions import UserError


class SaleRetentionReceivable(models.Model):
    _name = "sale.retention.receivable"
    _description = "Sale Retention Receivable"
    _order = "invoice_date desc, id desc"

    name = fields.Char(string="Reference", required=True, copy=False, readonly=True,
                       default=lambda self: self.env["ir.sequence"].next_by_code("sale.retention.receivable") or "New")
    partner_id = fields.Many2one("res.partner", string="Customer", required=True, readonly=True)
    sale_order_id = fields.Many2one("sale.order", string="Sale Order", readonly=True)
    invoice_id = fields.Many2one("account.move", string="Invoice", readonly=True,
                                 domain="[('move_type', '=', 'out_invoice')]")
    payment_id = fields.Many2one("account.payment", string="Payment", readonly=True)
    collection_move_ids = fields.Many2many(
        "account.move",
        "sale_retention_receivable_account_move_rel",
        "retention_id",
        "move_id",
        string="Collection Journal Entries",
        readonly=True,
        copy=False,
    )
    collection_move_count = fields.Integer(
        string="Collection Journal Entry Count",
        compute="_compute_collection_move_count",
    )
    currency_id = fields.Many2one("res.currency", string="Currency",
                                  default=lambda self: self.env.company.currency_id)
    company_id = fields.Many2one("res.company", string="Company",
                                 default=lambda self: self.env.company)
    retention_percent = fields.Float(string="Retention (%)", readonly=True)
    retention_amount = fields.Monetary(string="Retention Amount", readonly=True,
                                       currency_field="currency_id")
    collected_amount = fields.Monetary(string="Collected Amount", default=0.0,
                                       currency_field="currency_id")
    balance_amount = fields.Monetary(string="Balance", compute="_compute_balance",
                                     store=True, currency_field="currency_id")
    retention_account_id = fields.Many2one(
        "account.account",
        string="Retention Account",
        readonly=True,
        domain="[('account_type', 'in', ('asset_receivable', 'asset_current'))]",
    )
    invoice_date = fields.Date(string="Invoice Date", readonly=True)
    retention_due_date = fields.Date(string="Due Date")
    state = fields.Selection(
        string="State",
        selection=[
            ("draft", "Draft"),
            ("open", "Open"),
            ("partially_collected", "Partially Collected"),
            ("collected", "Collected"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        required=True,
        tracking=True,
    )

    @api.depends("retention_amount", "collected_amount")
    def _compute_balance(self):
        for rec in self:
            rec.balance_amount = rec.retention_amount - rec.collected_amount

    @api.depends("collection_move_ids")
    def _compute_collection_move_count(self):
        for rec in self:
            rec.collection_move_count = len(rec.collection_move_ids)

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        invoice_id = self.env.context.get("default_invoice_id")
        if not invoice_id:
            return vals

        invoice = self.env["account.move"].browse(invoice_id)
        if not invoice.exists():
            return vals

        sale_order = invoice._get_related_sale_order()
        account = invoice._get_retention_account()

        vals.setdefault("partner_id", invoice.commercial_partner_id.id)
        vals.setdefault("sale_order_id", sale_order.id if sale_order else False)
        vals.setdefault("invoice_id", invoice.id)
        vals.setdefault("retention_percent", invoice.retention_percent)
        vals.setdefault("retention_amount", invoice.retention_amount)
        vals.setdefault("retention_account_id", account.id if account else False)
        vals.setdefault("invoice_date", invoice.invoice_date)
        vals.setdefault("retention_due_date", invoice.retention_due_date)
        return vals

    def action_open(self):
        self.state = "open"

    def action_cancel(self):
        self.state = "cancelled"

    def action_draft(self):
        self.state = "draft"

    def action_open_collection_wizard(self):
        retentions = self
        if not retentions:
            retentions = self.env["sale.retention.receivable"].browse(
                self.env.context.get("active_ids", [])
            )

        retentions = retentions.filtered(
            lambda r: r.state in ("open", "partially_collected")
        )
        if not retentions:
            raise UserError("Please select at least one open retention record.")

        partners = retentions.mapped("partner_id")
        if len(partners) > 1:
            raise UserError(
                "Please select retention records for the same customer."
            )

        return {
            "type": "ir.actions.act_window",
            "name": "Collect Retention",
            "res_model": "sale.retention.collection.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                **self.env.context,
                "active_model": "sale.retention.receivable",
                "active_ids": retentions.ids,
                "default_partner_id": partners.id,
            },
        }

    def action_view_collection_moves(self):
        self.ensure_one()
        action = {
            "type": "ir.actions.act_window",
            "name": "Collection Journal Entries",
            "res_model": "account.move",
            "view_mode": "list,form",
            "domain": [("id", "in", self.collection_move_ids.ids)],
            "context": {"create": False},
        }
        if len(self.collection_move_ids) == 1:
            action["view_mode"] = "form"
            action["res_id"] = self.collection_move_ids.id
        return action

    def name_get(self):
        result = []
        for rec in self:
            name = rec.name or "New"
            if rec.partner_id:
                name = f"{name} - {rec.partner_id.display_name}"
            result.append((rec.id, name))
        return result
