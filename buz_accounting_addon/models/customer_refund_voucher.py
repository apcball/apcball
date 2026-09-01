# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class BuzCustomerRefundVoucher(models.Model):
    _name = "buz.customer.refund.voucher"
    _description = "Customer Refund Voucher (CV)"
    _order = "date desc, id desc"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _check_company_auto = True

    name = fields.Char(string="CV Number", readonly=True, copy=False, default="/", tracking=True)
    date = fields.Date(string="CV Date", default=fields.Date.context_today, required=True, tracking=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, tracking=True)
    currency_id = fields.Many2one("res.currency", related="company_id.currency_id", readonly=True, store=False)
    partner_id = fields.Many2one("res.partner", string="Customer", required=True, domain=[("customer_rank", ">", 0)], tracking=True, check_company=True)
    credit_note_id = fields.Many2one(
        "account.move",
        string="Customer Credit Note",
        required=True,
        domain="[('move_type','=','out_refund'),('state','=','posted'),('company_id','=',company_id)]",
        check_company=True,
        index=True,
        tracking=True,
    )
    cn_amount = fields.Monetary(string="CN Amount", currency_field="currency_id", related="credit_note_id.amount_total", readonly=True)
    cn_residual = fields.Monetary(string="CN Residual", currency_field="currency_id", compute="_compute_cn_residual", readonly=True, store=False)
    refund_amount = fields.Monetary(string="Refund Amount", currency_field="currency_id", required=True, tracking=True)
    # Alias for compatibility with reports
    amount_total = fields.Monetary(related="refund_amount", currency_field="currency_id", readonly=True)
    payment_type = fields.Selection([
        ("cash", "Cash"),
        ("transfer", "Transfer"),
        ("check", "Cheque"),
    ], string="Refund Method", default="transfer", required=True, tracking=True)
    destination_journal_id = fields.Many2one(
        "account.journal",
        string="Payment Journal",
        domain="[('type','in',('bank','cash')),('company_id','=',company_id)]",
        tracking=True,
        check_company=True,
    )
    payment_method_line_id = fields.Many2one(
        "account.payment.method.line",
        string="Payment Method",
        domain="[('payment_type','=','outbound'),('journal_id','=',destination_journal_id)]",
        tracking=True,
    )
    customer_account_id = fields.Many2one(
        "account.account",
        string="Customer Account",
        domain="[('account_type','=','asset_receivable')]",
        check_company=False,
        readonly=True,
        tracking=True,
    )
    billing_note = fields.Char(string="Billing Note", tracking=True)
    bank_free_dis = fields.Monetary(
        string="Bank Fee",
        currency_field="currency_id",
        help="Optional bank fee deducted by the bank.",
    )
    other_income_dis = fields.Monetary(
        string="Other Income",
        currency_field="currency_id",
        compute="_compute_other_income",
        store=True,
        readonly=True,
        help="CN residual less the actual refund amount.",
    )
    other_income_account_id = fields.Many2one("account.account", string="Other Income Account", domain="[('account_type', 'in', ['income', 'income_other']), ('company_id', '=', company_id)]", check_company=True, tracking=True, help="Account used for the write-off when the refund is below the CN residual.")
    check_number = fields.Char(string="Cheque Number", tracking=True)
    check_date = fields.Date(string="Cheque Date", tracking=True)
    check_pay_to = fields.Char(string="Pay to", tracking=True)
    refund_reason = fields.Text(string="Refund Reason", tracking=True)
    note = fields.Text(string="Internal Note")
    state = fields.Selection([
        ("draft", "Draft"),
        ("confirmed", "Confirmed"),
        ("registered", "Registered"),
        ("payment_cancelled", "Payment Cancelled"),
        ("cancel", "Cancelled"),
    ], default="draft", tracking=True, copy=False)
    payment_id = fields.Many2one("account.payment", string="Refund Payment", readonly=True, copy=False, index=True)
    payment_count = fields.Integer(compute="_compute_payment_count", string="Payments")
    line_ids = fields.One2many("buz.customer.refund.voucher.line", "voucher_id", string="Payment Lines", copy=False)
    bank_transfer_ids = fields.One2many(
        "account.bank.transfer",
        "buz_customer_refund_voucher_id",
        string="Bank Transfers",
        copy=False,
    )
    # PV-parity computed totals (CV-specific logic, nullable/zero-safe)
    amount_total_gross = fields.Monetary(string="Total Gross", currency_field="currency_id", compute="_compute_cv_totals", store=True)
    amount_total_net = fields.Monetary(string="Total Net", currency_field="currency_id", compute="_compute_cv_totals", store=True)
    amount_total_net_display = fields.Monetary(string="Total Net Display", currency_field="currency_id", compute="_compute_cv_display")

    # Uniqueness enforced via Python _check_one_active_per_cn (avoid btree_gist requirement)

    @api.depends("credit_note_id.amount_residual", "credit_note_id.amount_residual_signed", "credit_note_id.amount_total")
    def _compute_cn_residual(self):
        for rec in self:
            if rec.credit_note_id:
                rec.cn_residual = abs(rec.credit_note_id.amount_residual_signed) if hasattr(rec.credit_note_id, 'amount_residual_signed') and rec.credit_note_id.amount_residual_signed is not None else abs(rec.credit_note_id.amount_residual or 0.0)
            else:
                rec.cn_residual = 0.0

    @api.depends("payment_id")
    def _compute_payment_count(self):
        for rec in self:
            rec.payment_count = 1 if rec.payment_id else 0

    @api.depends("credit_note_id.amount_residual", "credit_note_id.amount_residual_signed", "refund_amount")
    def _compute_other_income(self):
        for rec in self:
            rec.other_income_dis = max((rec.cn_residual or 0.0) - (rec.refund_amount or 0.0), 0.0)

    def _validate_refund_amount(self, residual=None):
        self.ensure_one()
        residual = self.cn_residual if residual is None else residual
        if self.refund_amount < 0.01:
            raise UserError(_("Refund Amount must be greater than 0."))
        if self.refund_amount - residual > 0.01:
            raise UserError(_("Refund Amount (%.2f) cannot exceed Credit Note residual (%.2f).") % (self.refund_amount, residual))
        return residual

    @api.depends("line_ids.refund_amount", "refund_amount", "bank_free_dis", "other_income_dis")
    def _compute_cv_totals(self):
        """CV-specific totals โ€” independent from PV logic. Gross = sum lines or refund_amount."""
        for rec in self:
            gross = sum(rec.line_ids.mapped("refund_amount")) if rec.line_ids else (rec.refund_amount or 0.0)
            rec.amount_total_gross = gross
            # CV net = gross - bank fee - other income (nullable, zero-safe)
            rec.amount_total_net = gross - (rec.bank_free_dis or 0.0) - (rec.other_income_dis or 0.0)

    @api.depends("amount_total_net", "bank_transfer_ids.amount", "amount_total_gross")
    def _compute_cv_display(self):
        for rec in self:
            bt_total = sum(rec.bank_transfer_ids.mapped("amount")) if rec.bank_transfer_ids else 0.0
            rec.amount_total_net_display = rec.amount_total_net or bt_total or rec.amount_total_gross

    @api.onchange("credit_note_id")
    def _onchange_credit_note_id(self):
        if self.credit_note_id:
            # enforce company match
            if self.company_id and self.credit_note_id.company_id != self.company_id:
                # auto align company
                self.company_id = self.credit_note_id.company_id
            self.partner_id = self.credit_note_id.partner_id
            # amount is absolute residual signed
            residual = abs(self.credit_note_id.amount_residual_signed) if hasattr(self.credit_note_id, 'amount_residual_signed') else abs(self.credit_note_id.amount_residual)
            self.refund_amount = residual
            # default customer account from credit note receivable line
            rec_line = self.credit_note_id.line_ids.filtered(lambda l: l.account_id.account_type == 'asset_receivable')[:1]
            self.customer_account_id = rec_line.account_id if rec_line else self.credit_note_id.partner_id.property_account_receivable_id
            if not self.check_pay_to and self.partner_id:
                self.check_pay_to = self.partner_id.name

    @api.onchange("destination_journal_id")
    def _onchange_destination_journal_id(self):
        if self.destination_journal_id:
            # reset method if incompatible
            if self.payment_method_line_id and self.payment_method_line_id.journal_id != self.destination_journal_id:
                self.payment_method_line_id = False

    @api.onchange("refund_amount")
    def _onchange_refund_amount_sync_line(self):
        if self.line_ids:
            self.line_ids[0].refund_amount = self.refund_amount

    @api.onchange("partner_id")
    def _onchange_partner_check_pay_to(self):
        if self.partner_id and not self.check_pay_to:
            self.check_pay_to = self.partner_id.name

    def _sync_lines(self):
        """Ensure single line per CV from CN โ€” editable Refund Amount, supports Partial."""
        for rec in self:
            if not rec.credit_note_id:
                continue
            residual = abs(rec.credit_note_id.amount_residual_signed) if hasattr(rec.credit_note_id, 'amount_residual_signed') and rec.credit_note_id.amount_residual_signed is not None else abs(rec.credit_note_id.amount_residual)
            if not rec.line_ids:
                self.env["buz.customer.refund.voucher.line"].create({
                    "voucher_id": rec.id,
                    "credit_note_id": rec.credit_note_id.id,
                    "refund_amount": rec.refund_amount or residual,
                })
            else:
                # Single-CN MVP: keep header and line in sync, but allow Partial (user edits either side)
                line = rec.line_ids[0]
                vals = {}
                if line.credit_note_id != rec.credit_note_id:
                    vals["credit_note_id"] = rec.credit_note_id.id
                # Do not auto-overwrite if user already set partial within residual; only sync when header changed explicitly
                vals["refund_amount"] = rec.refund_amount
                line.write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "/") in ("/", False, None):
                company = self.env["res.company"].browse(vals.get("company_id")) if vals.get("company_id") else self.env.company
                # per company yearly sequence: use with_company and sequence_date
                seq_date = vals.get("date") or fields.Date.context_today(self)
                seq = self.env["ir.sequence"].with_company(company).next_by_code("buz.customer.refund.voucher", sequence_date=seq_date) or "/"
                vals["name"] = seq
            # set refund_amount from credit note if not provided
            if vals.get("credit_note_id") and not vals.get("refund_amount"):
                cn = self.env["account.move"].browse(vals["credit_note_id"])
                if cn.exists():
                    residual = abs(cn.amount_residual_signed) if hasattr(cn, 'amount_residual_signed') and cn.amount_residual_signed is not None else abs(cn.amount_residual)
                    vals["refund_amount"] = residual
                    if not vals.get("partner_id"):
                        vals["partner_id"] = cn.partner_id.id
            if vals.get("credit_note_id") and not vals.get("customer_account_id"):
                cn = self.env["account.move"].browse(vals["credit_note_id"])
                rec_line = cn.line_ids.filtered(lambda line: line.account_id.account_type == "asset_receivable")[:1]
                vals["customer_account_id"] = (rec_line.account_id if rec_line else cn.partner_id.property_account_receivable_id).id

            if "date" not in vals or not vals["date"]:
                vals["date"] = fields.Date.context_today(self)
        records = super().create(vals_list)
        # auto create single payment line
        for rec in records:
            rec._sync_lines()
        return records

    def write(self, vals):
        # allow Partial: refund_amount must be >0 and <= CN residual
        if "refund_amount" in vals:
            for rec in self:
                if rec.state not in ("draft", "confirmed"):
                    raise UserError(_("Refund Amount cannot be changed after Confirmed."))
                target_cn = self.env["account.move"].browse(vals.get("credit_note_id")) if vals.get("credit_note_id") else rec.credit_note_id
                if target_cn:
                    residual = abs(target_cn.amount_residual_signed) if hasattr(target_cn, 'amount_residual_signed') else abs(target_cn.amount_residual)
                    new_amount = vals["refund_amount"]
                    if new_amount < 0.01:
                        raise UserError(_("Refund Amount must be greater than 0."))
                    if new_amount - residual > 0.01:
                        raise UserError(_("Refund Amount (%.2f) cannot exceed Credit Note residual (%.2f).") % (new_amount, residual))
                # keep line in sync with header for single-CN MVP
                # will sync after write
        # prevent changing credit_note after creation except draft
        if "credit_note_id" in vals:
            for rec in self:
                if rec.state != "draft":
                    raise UserError(_("Cannot change Credit Note after Draft."))
        # handle name /
        if vals.get("name") == "/":
            for rec in self:
                vals["name"] = self.env["ir.sequence"].with_company(rec.company_id).next_by_code("buz.customer.refund.voucher", sequence_date=vals.get("date") or rec.date) or "/"
        res = super().write(vals)
        # keep line in sync when credit_note or amount changes (header -> line)
        if "refund_amount" in vals:
            for rec in self:
                if rec.line_ids:
                    # sync first line to header amount (Partial supported โ€” header is source for payment)
                    line = rec.line_ids[0]
                    if abs((line.refund_amount or 0) - vals["refund_amount"]) > 0.01:
                        line.write({"refund_amount": vals["refund_amount"]})
        if "credit_note_id" in vals:
            for rec in self:
                rec._sync_lines()
        return res

    @api.constrains("credit_note_id", "company_id", "partner_id", "refund_amount", "refund_reason", "other_income_account_id", "state", "line_ids")
    def _check_credit_note_validity(self):
        for rec in self:
            cn = rec.credit_note_id
            if not cn:
                continue
            # must be out_refund posted
            if cn.move_type != "out_refund":
                raise ValidationError(_("Credit Note %s must be of type Customer Credit Note (out_refund).") % cn.name)
            if cn.state != "posted":
                raise ValidationError(_("Credit Note %s must be Posted.") % cn.name)
            if cn.company_id != rec.company_id:
                raise ValidationError(_("Credit Note %s belongs to company %s, but CV is for %s.") % (cn.name, cn.company_id.name, rec.company_id.name))
            if rec.partner_id and cn.partner_id != rec.partner_id:
                raise ValidationError(_("CV customer must match Credit Note customer."))
            cn_receivable = cn.line_ids.filtered(lambda line: line.account_id.account_type == "asset_receivable")[:1]
            expected_account = cn_receivable.account_id if cn_receivable else cn.partner_id.property_account_receivable_id
            if rec.customer_account_id and rec.customer_account_id != expected_account:
                raise ValidationError(_("Customer Account must match the receivable account on the Credit Note."))
            # residual > 0
            residual = abs(cn.amount_residual_signed) if hasattr(cn, 'amount_residual_signed') else abs(cn.amount_residual)
            if residual < 0.01 and rec.state in ("draft", "confirmed"):
                raise ValidationError(_("Credit Note %s has no residual amount.") % cn.name)
            # Partial support: header must be >0 and <= residual; line sum must also <= residual and = header
            if rec.state in ("draft", "confirmed"):
                if rec.refund_amount < 0.01:
                    raise ValidationError(_("Refund Amount must be greater than 0."))
                if rec.refund_amount - residual > 0.01:
                    raise ValidationError(_("Refund Amount (%.2f) cannot exceed Credit Note residual (%.2f).") % (rec.refund_amount, residual))
                if rec.line_ids:
                    line_total = sum(rec.line_ids.mapped("refund_amount"))
                    if abs(line_total - rec.refund_amount) > 0.01:
                        raise ValidationError(_("Payment Lines total (%.2f) must match Refund Amount (%.2f).") % (line_total, rec.refund_amount))
                    if line_total - residual > 0.01:
                        raise ValidationError(_("Payment Lines total (%.2f) cannot exceed Credit Note residual (%.2f).") % (line_total, residual))
                    for line in rec.line_ids:
                        if line.refund_amount < 0.01:
                            raise ValidationError(_("Line Refund Amount must be greater than 0."))
                        if line.refund_amount - residual > 0.01:
                            raise ValidationError(_("Line Refund Amount (%.2f) cannot exceed Credit Note residual (%.2f).") % (line.refund_amount, residual))
            # locked period / company_ids check
            if not self.env.user.has_group("base.group_system"):
                # company access
                if rec.company_id not in self.env.companies:
                    raise ValidationError(_("You do not have access to company %s.") % rec.company_id.name)
            # ACL handled by access.csv; additional company_ids check
            # currency check
            if rec.currency_id != rec.company_id.currency_id:
                raise ValidationError(_("Currency must match company currency."))
            if rec.other_income_dis > 0.01 and not rec.other_income_account_id:
                raise ValidationError(_("Other Income Account is required for a partial refund."))
            if rec.other_income_dis > 0.01 and not rec.refund_reason:
                raise ValidationError(_("Refund Reason is required for a partial refund."))

    @api.constrains("destination_journal_id", "payment_method_line_id", "payment_type", "company_id")
    def _check_journal_payment_method(self):
        for rec in self:
            if rec.destination_journal_id and rec.destination_journal_id.company_id != rec.company_id:
                raise ValidationError(_("Payment Journal must belong to the same company as the CV."))
            if rec.payment_method_line_id and rec.destination_journal_id and rec.payment_method_line_id.journal_id != rec.destination_journal_id:
                raise ValidationError(_("Payment Method does not belong to the selected journal."))
            if rec.payment_method_line_id and rec.payment_method_line_id.payment_type != "outbound":
                raise ValidationError(_("Payment Method must be Outbound."))
            if rec.state in ("confirmed", "registered") and not rec.destination_journal_id:
                raise ValidationError(_("Payment Journal is required before registration."))
            if rec.state in ("confirmed", "registered") and not rec.payment_method_line_id:
                raise ValidationError(_("Outbound Payment Method is required before registration."))

    @api.constrains("credit_note_id", "state")
    def _check_one_active_per_cn(self):
        for rec in self:
            if rec.state in ("draft", "confirmed", "registered"):
                others = self.search([
                    ("credit_note_id", "=", rec.credit_note_id.id),
                    ("id", "!=", rec.id),
                    ("state", "in", ["draft", "confirmed", "registered"]),
                ], limit=1)
                if others:
                    raise ValidationError(_("An active CV (%s) already exists for Credit Note %s.") % (others.name, rec.credit_note_id.name))

    def action_print_cv(self):
        """Print current CV data directly โ€” no revision/snapshot."""
        self.ensure_one()
        if self.state not in ("draft", "confirmed", "registered", "payment_cancelled"):
            raise UserError(_("Printing is only allowed in Draft/Confirmed/Registered."))
        self._check_company_access()
        self.message_post(body=_("CV printed โ€” internal copy."))
        return self.env.ref("buz_accounting_addon.action_report_buz_customer_refund_voucher").report_action(self)

    def action_confirm(self):
        """Draft -> Confirmed. No print requirement."""
        for rec in self:
            if rec.state != "draft":
                continue
            rec._check_company_access()
            # No revision requirement โ€” print is optional per updated spec
            if not rec.destination_journal_id:
                raise UserError(_("Payment Journal is required before confirming the CV."))
            if not rec.payment_method_line_id:
                raise UserError(_("Outbound Payment Method is required before confirming the CV."))
            if rec.payment_method_line_id.journal_id != rec.destination_journal_id or rec.payment_method_line_id.payment_type != "outbound":
                raise UserError(_("Select an Outbound Payment Method from the selected journal."))
            if rec.other_income_dis > 0.01 and not rec.refund_reason:
                raise UserError(_("Refund Reason is required for a partial refund."))
            rec.write({"state": "confirmed"})
            rec.message_post(body=_("CV Confirmed."))
        return True

    def action_register_refund(self):
        """Open standard account.payment.register wizard for this CV's credit note. Single transaction."""
        self.ensure_one()
        if self.state != "confirmed":
            raise UserError(_("Only Confirmed CV can register refund."))
        self._check_company_access()
        self.env.cr.execute("SELECT id FROM buz_customer_refund_voucher WHERE id = %s FOR UPDATE", (self.id,))
        self.invalidate_recordset(["payment_id", "state"])
        existing_payment = self.env["account.payment"].search(
            [
                ("buz_customer_refund_voucher_id", "=", self.id),
                ("state", "!=", "cancel"),
            ],
            limit=1,
        )
        if existing_payment:
            raise UserError(_("A non-cancelled refund payment already exists for this CV."))
        if not self.destination_journal_id:
            raise UserError(_("Payment Journal is required before registering the refund."))
        if not self.payment_method_line_id:
            raise UserError(_("Outbound Payment Method is required before registering the refund."))
        if self.payment_method_line_id.journal_id != self.destination_journal_id or self.payment_method_line_id.payment_type != "outbound":
            raise UserError(_("Select an Outbound Payment Method from the selected journal."))
        # ensure CV's credit note still has residual and not already fully reconciled
        cn = self.credit_note_id
        residual = abs(cn.amount_residual_signed) if hasattr(cn, 'amount_residual_signed') else abs(cn.amount_residual)
        if residual < 0.01:
            raise UserError(_("Credit Note %s has no residual to refund.") % cn.name)
        if self.refund_amount < 0.01:
            raise UserError(_("Refund Amount must be greater than 0."))
        if self.refund_amount - residual > 0.01:
            raise UserError(_("Refund Amount (%.2f) cannot exceed Credit Note residual (%.2f).") % (self.refund_amount, residual))
        if residual - self.refund_amount > 0.01 and not self.other_income_account_id:
            raise UserError(_("Select Other Income Account before registering a partial refund."))
        if residual - self.refund_amount > 0.01 and not self.refund_reason:
            raise UserError(_("Refund Reason is required for a partial refund."))
        ctx = {
            "active_model": "account.move",
            "active_ids": cn.ids,
            "active_id": cn.id,
            "default_partner_id": self.partner_id.id,
            "default_payment_type": "outbound",
            "default_partner_type": "customer",
            "default_amount": self.refund_amount,
            "default_communication": cn.name,
            "default_ref": f"CV {self.name}",
            "default_company_id": self.company_id.id,
            "default_currency_id": self.currency_id.id,
            "buz_cv_id": self.id,
            "buz_cv_ref": f"CV {self.name}",
        }
        if self.destination_journal_id:
            ctx["default_journal_id"] = self.destination_journal_id.id
        if self.payment_method_line_id:
            ctx["default_payment_method_line_id"] = self.payment_method_line_id.id
        # journal/payment method line optional for cash
        return {
            "name": _("Register Refund"),
            "res_model": "account.payment.register",
            "view_mode": "form",
            "view_id": self.env.ref("account.view_account_payment_register_form").id,
            "target": "new",
            "type": "ir.actions.act_window",
            "context": ctx,
        }

    def _create_refund_payment(self):
        """Internal: called from payment.register override in transaction."""
        # This is not directly called; payment register will create payment and link
        pass

    def action_cancel(self):
        """Cancel CV โ€” only Manager can. Allowed from draft/confirmed."""
        for rec in self:
            if rec.state not in ("draft", "confirmed", "payment_cancelled"):
                raise UserError(_("Only Draft/Confirmed/Payment Cancelled CV can be cancelled."))
            # ACL check: only manager
            if not self.env.user.has_group("account.group_account_manager"):
                raise UserError(_("Only Accounting Manager can cancel CV."))
            rec._check_company_access()
            rec.write({"state": "cancel"})
            rec.message_post(body=_("CV Cancelled."))
        return True

    def action_reset_to_draft(self):
        """Reset to draft โ€” manager only. From confirmed/cancel/payment_cancelled."""
        for rec in self:
            if rec.state not in ("confirmed", "cancel", "payment_cancelled"):
                continue
            if not self.env.user.has_group("account.group_account_manager"):
                raise UserError(_("Only Accounting Manager can reset CV to draft."))
            rec.write({"state": "draft"})
            rec.message_post(body=_("CV Reset to Draft."))
        return True

    def action_open_payment(self):
        self.ensure_one()
        if not self.payment_id:
            raise UserError(_("No payment linked to this CV."))
        return {
            "name": _("Refund Payment"),
            "type": "ir.actions.act_window",
            "res_model": "account.payment",
            "view_mode": "form",
            "res_id": self.payment_id.id,
            "target": "current",
        }

    def action_open_credit_note(self):
        self.ensure_one()
        return {
            "name": _("Credit Note"),
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "view_mode": "form",
            "res_id": self.credit_note_id.id,
            "target": "current",
        }

    def _check_company_access(self):
        for rec in self:
            if rec.company_id not in self.env.companies:
                raise UserError(_("Access denied for company %s.") % rec.company_id.name)
            # locked period check (fiscal year lock)
            lock_date = rec.company_id.period_lock_date or rec.company_id.fiscalyear_lock_date
            if lock_date and rec.date and rec.date <= lock_date:
                raise UserError(_("CV date is in a locked period (lock date: %s).") % lock_date)

    def unlink(self):
        for rec in self:
            if rec.state != "draft":
                raise UserError(_("Only Draft CV can be deleted."))
        return super().unlink()


class BuzCustomerRefundVoucherLine(models.Model):
    _name = "buz.customer.refund.voucher.line"
    _description = "Customer Refund Voucher Line (editable Refund Amount, Partial)"
    _check_company_auto = True

    voucher_id = fields.Many2one("buz.customer.refund.voucher", string="CV", required=True, ondelete="cascade", index=True, readonly=True)
    company_id = fields.Many2one(related="voucher_id.company_id", store=True, readonly=True)
    currency_id = fields.Many2one(related="voucher_id.currency_id", readonly=True)
    credit_note_id = fields.Many2one("account.move", string="Credit Note", domain="[('move_type','=','out_refund')]", readonly=True, index=True, check_company=True)
    partner_id = fields.Many2one(related="voucher_id.partner_id", readonly=True, store=False)
    cn_amount = fields.Monetary(string="CN Amount", related="credit_note_id.amount_total", readonly=True, currency_field="currency_id")
    refund_amount = fields.Monetary(string="Refund Amount", currency_field="currency_id", required=True)
    payment_state = fields.Selection(related="credit_note_id.payment_state", string="Payment Status", readonly=True, store=False)

    _sql_constraints = [
        ("uniq_voucher_credit_note", "unique(voucher_id, credit_note_id)", "Duplicate credit note in CV lines."),
    ]

    @api.constrains("refund_amount", "credit_note_id", "voucher_id")
    def _check_refund_limit(self):
        for line in self:
            if not line.credit_note_id or not line.voucher_id:
                continue
            cn = line.credit_note_id
            residual = abs(cn.amount_residual_signed) if hasattr(cn, 'amount_residual_signed') and cn.amount_residual_signed is not None else abs(cn.amount_residual or 0.0)
            if line.refund_amount < 0.01:
                raise ValidationError(_("Line Refund Amount must be greater than 0."))
            if line.refund_amount - residual > 0.01:
                raise ValidationError(_("Line Refund Amount (%.2f) cannot exceed Credit Note residual (%.2f) (%s).") % (line.refund_amount, residual, cn.name))

    def write(self, vals):
        # limit refund_amount edits to draft/confirmed only; Partial allowed
        if "refund_amount" in vals:
            for line in self:
                if line.voucher_id.state not in ("draft", "confirmed"):
                    raise UserError(_("Cannot change Refund Amount after Confirmed."))
        res = super().write(vals)
        if "refund_amount" in vals:
            # keep header in sync (single-CN MVP) โ€” header = line total
            for vid in self.mapped("voucher_id"):
                if vid.state in ("draft", "confirmed"):
                    line_total = sum(vid.line_ids.mapped("refund_amount"))
                    if abs((vid.refund_amount or 0) - line_total) > 0.01:
                        vid.write({"refund_amount": line_total})
        return res
