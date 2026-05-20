from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = "account.move"

    _RETENTION_ALLOWED_ACCOUNT_TYPES = ("asset_receivable", "asset_current")

    retention_enabled = fields.Boolean(string="Retention")
    retention_percent = fields.Float(string="Retention (%)")
    retention_days = fields.Integer(string="Retention Days")
    retention_amount = fields.Monetary(string="Retention Amount", currency_field="currency_id")
    retention_due_date = fields.Date(string="Retention Due Date")
    retention_record_ids = fields.One2many(
        "sale.retention.receivable",
        "invoice_id",
        string="Retention Records",
    )
    retention_record_count = fields.Integer(
        string="Retention Record Count",
        compute="_compute_retention_record_count",
    )
    retention_state = fields.Selection(
        string="Retention State",
        selection=[
            ("none", "No Retention"),
            ("pending", "Pending"),
            ("open", "Open"),
            ("partially_collected", "Partially Collected"),
            ("collected", "Collected"),
        ],
        compute="_compute_retention_state",
        store=True,
    )

    @api.depends("retention_enabled", "retention_record_ids.state")
    def _compute_retention_state(self):
        for move in self:
            if not move.retention_enabled:
                move.retention_state = "none"
                continue
            records = move.retention_record_ids
            if not records:
                move.retention_state = "pending"
                continue
            states = set(records.mapped("state"))
            if states == {"collected"}:
                move.retention_state = "collected"
            elif "partially_collected" in states:
                move.retention_state = "partially_collected"
            elif "open" in states:
                move.retention_state = "open"
            else:
                move.retention_state = "pending"

    @api.depends("retention_record_ids")
    def _compute_retention_record_count(self):
        for move in self:
            move.retention_record_count = len(move.retention_record_ids)

    def _get_invoice_retention_defaults(self):
        """Return retention defaults from sale order if originating from one."""
        self.ensure_one()
        if self.invoice_origin:
            sale = self.env["sale.order"].search(
                [("name", "=", self.invoice_origin)], limit=1
            )
            if sale and sale.retention_enabled:
                return {
                    "retention_enabled": sale.retention_enabled,
                    "retention_percent": sale.retention_percent,
                    "retention_days": sale.retention_days,
                    "retention_amount": sale.retention_amount,
                    "retention_due_date": sale.retention_due_date,
                }
        return {}

    def _get_related_sale_order(self):
        self.ensure_one()
        sale_order = self.invoice_line_ids.mapped("sale_line_ids.order_id")[:1]
        if sale_order:
            return sale_order
        if self.invoice_origin:
            return self.env["sale.order"].search(
                [("name", "=", self.invoice_origin)],
                limit=1,
            )
        return self.env["sale.order"]

    def _prepare_retention_record_defaults(self):
        self.ensure_one()
        sale_order = self._get_related_sale_order()
        account = self._get_retention_account()
        return {
            "default_partner_id": self.commercial_partner_id.id,
            "default_sale_order_id": sale_order.id if sale_order else False,
            "default_invoice_id": self.id,
            "default_retention_percent": self.retention_percent,
            "default_retention_amount": self.retention_amount,
            "default_retention_account_id": account.id if account else False,
            "default_invoice_date": self.invoice_date,
            "default_retention_due_date": self.retention_due_date,
            "default_state": "draft",
        }

    def _check_retention_account_type(self, account):
        self.ensure_one()
        if account and account.account_type not in self._RETENTION_ALLOWED_ACCOUNT_TYPES:
            raise UserError(
                _(
                    "Retention Receivable account must be a Receivable or Current Asset account."
                )
            )

    def action_open_retention_records(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "sale_retention_receivable.action_sale_retention_receivable_from_invoice"
        )
        action["domain"] = [("invoice_id", "=", self.id)]
        action["context"] = {
            **self.env.context,
            **self._prepare_retention_record_defaults(),
            "create": True,
        }

        if len(self.retention_record_ids) == 1:
            action["view_mode"] = "form"
            action["res_id"] = self.retention_record_ids.id
            action["views"] = [
                (
                    self.env.ref(
                        "sale_retention_receivable.view_sale_retention_receivable_form"
                    ).id,
                    "form",
                )
            ]
        elif not self.retention_record_ids:
            action["view_mode"] = "form"
            action["views"] = [
                (
                    self.env.ref(
                        "sale_retention_receivable.view_sale_retention_receivable_form"
                    ).id,
                    "form",
                )
            ]
        return action

    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        for move, vals in zip(moves, vals_list):
            if move.move_type in ("out_invoice", "out_refund") and not move.retention_enabled:
                defaults = move._get_invoice_retention_defaults()
                if defaults:
                    move.write(defaults)
        return moves

    @api.model
    def _get_retention_account(self):
        """Get the retention receivable account for the current company."""
        ICP = self.env["ir.config_parameter"].sudo()
        account_id = ICP.get_param("sale_retention_receivable.default_account_id")
        if account_id:
            return self.env["account.account"].browse(int(account_id))
        return None

    def action_post(self):
        res = super().action_post()
        for move in self:
            if move.move_type in ("out_invoice", "out_refund") and move.retention_enabled:
                if not move.retention_amount:
                    continue
                account = move._get_retention_account()
                if not account:
                    raise UserError(
                        _("Retention Receivable account is not configured.\n"
                          "Please set it in Accounting > Configuration > Settings.")
                    )
                move._check_retention_account_type(account)
        return res

    @api.constrains("retention_percent")
    def _check_retention_percent(self):
        for move in self:
            if move.retention_enabled and move.retention_percent:
                if move.retention_percent < 0.0 or move.retention_percent > 100.0:
                    raise UserError(
                        _("Retention percentage must be between 0 and 100.")
                    )


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    retention_receivable_id = fields.Many2one(
        "sale.retention.receivable",
        string="Retention Receivable",
        ondelete="set null",
    )
