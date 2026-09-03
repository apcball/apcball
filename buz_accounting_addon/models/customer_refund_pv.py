# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class BuzCustomerRefundPv(models.Model):
    _name = "buz.customer.refund.pv"
    _description = "Customer Refund PV (Phase 1 - Draft only)"
    _order = "date desc, id desc"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _check_company_auto = True

    name = fields.Char(string="Refund PV Number", readonly=True, copy=False, default="/", tracking=True)
    date = fields.Date(string="PV Date", default=fields.Date.context_today, required=True, tracking=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, tracking=True)
    currency_id = fields.Many2one("res.currency", related="company_id.currency_id", readonly=True, store=True)
    partner_id = fields.Many2one("res.partner", string="Customer", required=True, domain=[("customer_rank", ">", 0)], tracking=True, check_company=True)
    credit_note_id = fields.Many2one(
        "account.move",
        string="Customer Credit Note",
        domain="[('move_type', '=', 'out_refund'), ('state', '=', 'posted')]",
        check_company=True,
        index=True,
        tracking=True,
        help="Originating Customer Credit Note (readonly after creation)",
    )
    state = fields.Selection([
        ("draft", "Draft"),
        ("posted", "Posted"),
        ("cancel", "Cancelled"),
    ], default="draft", tracking=True)

    # Payment planning fields — mirror Vendor PV for layout parity
    payment_type = fields.Selection([
        ("cash", "Cash"),
        ("transfer", "Transfer"),
        ("check", "Check"),
    ], string="Payment Type", default="transfer", tracking=True)
    destination_journal_id = fields.Many2one(
        "account.journal",
        string="Payment Journal",
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]",
        tracking=True,
        check_company=True,
    )
    payment_method_line_id = fields.Many2one(
        "account.payment.method.line",
        string="Payment Method",
        domain="[('payment_type', '=', 'outbound'), ('journal_id', '=', destination_journal_id)]",
        tracking=True,
    )
    bank_free_dis = fields.Monetary(string="Bank Fee", currency_field="currency_id")
    other_income_dis = fields.Monetary(string="Other Income", currency_field="currency_id")
    check_number = fields.Char(string="Cheque Number", tracking=True)
    check_date = fields.Date(string="Cheque Date", tracking=True)
    check_pay_to = fields.Char(string="Pay to", tracking=True)

    note = fields.Text(string="Note")

    line_ids = fields.One2many("buz.customer.refund.pv.line", "pv_id", string="Refund Lines")

    # Totals — mirror Vendor PV computations for report/layout parity
    amount_total_gross = fields.Monetary(string="Total Gross", currency_field="currency_id", compute="_compute_amount_totals", store=True)
    amount_total_wht = fields.Monetary(string="Total WHT", currency_field="currency_id", compute="_compute_amount_totals", store=True)
    amount_total_net = fields.Monetary(string="Total Net", currency_field="currency_id", compute="_compute_amount_totals", store=True)
    amount_total_net_display = fields.Monetary(string="Total Net Display", currency_field="currency_id", compute="_compute_amount_totals")

    @api.onchange("destination_journal_id")
    def _onchange_destination_journal_id(self):
        self.payment_method_line_id = False

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        if self.partner_id and not self.check_pay_to:
            self.check_pay_to = self.partner_id.name

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "/") in ("/", False, None):
                vals["name"] = self.env["ir.sequence"].next_by_code("buz.customer.refund.pv") or "/"
            if "date" not in vals or not vals["date"]:
                vals["date"] = fields.Date.context_today(self)
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("name") == "/":
            vals["name"] = self.env["ir.sequence"].next_by_code("buz.customer.refund.pv") or "/"
        return super().write(vals)

    @api.depends("line_ids.amount_to_pay_gross", "line_ids.wht_amount", "bank_free_dis", "other_income_dis")
    def _compute_amount_totals(self):
        for pv in self:
            line_gross = sum(line.amount_to_pay_gross for line in pv.line_ids)
            line_wht = sum(line.wht_amount for line in pv.line_ids)
            line_net = sum(line.amount_to_pay_net for line in pv.line_ids)
            pv.amount_total_gross = line_gross
            pv.amount_total_wht = line_wht
            pv.amount_total_net = line_net
            pv.amount_total_net_display = line_net

    def action_open_credit_note(self):
        self.ensure_one()
        if not self.credit_note_id:
            raise UserError(_("No credit note linked."))
        return {
            "name": _("Customer Credit Note"),
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "view_mode": "form",
            "res_id": self.credit_note_id.id,
            "target": "current",
        }


class BuzCustomerRefundPvLine(models.Model):
    _name = "buz.customer.refund.pv.line"
    _description = "Customer Refund PV Line"

    pv_id = fields.Many2one("buz.customer.refund.pv", string="Refund PV", required=True, ondelete="cascade")
    partner_id = fields.Many2one("res.partner", string="Customer", related="pv_id.partner_id", store=True, readonly=True)
    move_id = fields.Many2one(
        "account.move",
        string="Credit Note",
        domain="[('partner_id', '=', partner_id), ('move_type', '=', 'out_refund'), ('state', '=', 'posted')]",
    )

    # Amount snapshots (signed helpers mirror Vendor PV)
    amount_total_signed = fields.Monetary(string="Total Amount", currency_field="currency_id", related="move_id.amount_total_signed", readonly=True)
    amount_residual_signed = fields.Monetary(string="Residual Amount", currency_field="currency_id", related="move_id.amount_residual_signed", readonly=True)

    amount_to_pay_gross = fields.Monetary(
        string="Amount to Refund (Gross)",
        currency_field="currency_id",
        default=0.0,
    )
    buz_wht_tax_id = fields.Many2one("account.withholding.tax", string="WHT Tax", check_company=True)
    wht_base_amount = fields.Monetary(string="WHT Base Amount", currency_field="currency_id", default=0.0)
    wht_rate = fields.Float(string="WHT Rate", default=0.0)
    wht_amount = fields.Monetary(string="WHT Amount", currency_field="currency_id", compute="_compute_wht_amount", store=True)
    amount_to_pay_net = fields.Monetary(string="Amount to Refund (Net)", currency_field="currency_id", compute="_compute_amount_to_pay_net", store=True)

    currency_id = fields.Many2one(related="pv_id.currency_id", store=True, readonly=True)
    company_id = fields.Many2one(related="pv_id.company_id", store=True, readonly=True)

    @api.onchange("move_id")
    def _onchange_move_id(self):
        if self.move_id:
            self.amount_to_pay_gross = abs(self.move_id.amount_residual_signed) if hasattr(self.move_id, "amount_residual_signed") else abs(self.move_id.amount_residual)
            # Untaxed base for WHT parity (if available)
            try:
                self.wht_base_amount = abs(self.move_id.amount_untaxed_signed) if hasattr(self.move_id, "amount_untaxed_signed") else abs(self.move_id.amount_untaxed)
            except Exception:
                self.wht_base_amount = self.amount_to_pay_gross

    @api.onchange("buz_wht_tax_id")
    def _onchange_wht_tax(self):
        if self.buz_wht_tax_id:
            self.wht_rate = (self.buz_wht_tax_id.amount or 0.0) / 100.0
        else:
            self.wht_rate = 0.0

    @api.depends("wht_base_amount", "wht_rate", "buz_wht_tax_id")
    def _compute_wht_amount(self):
        for line in self:
            line.wht_amount = abs(line.wht_base_amount * (line.wht_rate or 0.0))

    @api.depends("amount_to_pay_gross", "wht_amount")
    def _compute_amount_to_pay_net(self):
        for line in self:
            line.amount_to_pay_net = line.amount_to_pay_gross - abs(line.wht_amount)
