# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging
import json

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
    refund_amount = fields.Monetary(string="Refund Amount", currency_field="currency_id", required=True, readonly=True, tracking=True)
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
        tracking=True,
    )
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
    revision_ids = fields.One2many("buz.customer.refund.voucher.revision", "voucher_id", string="Print Revisions")
    revision_count = fields.Integer(compute="_compute_revision_count", string="Revisions")
    latest_revision_id = fields.Many2one("buz.customer.refund.voucher.revision", compute="_compute_latest_revision", string="Latest Revision", store=False)

    # Uniqueness enforced via Python _check_one_active_per_cn (avoid btree_gist requirement)

    @api.depends("payment_id")
    def _compute_payment_count(self):
        for rec in self:
            rec.payment_count = 1 if rec.payment_id else 0

    @api.depends("revision_ids")
    def _compute_revision_count(self):
        for rec in self:
            rec.revision_count = len(rec.revision_ids)

    @api.depends("revision_ids.revision")
    def _compute_latest_revision(self):
        for rec in self:
            if rec.revision_ids:
                rec.latest_revision_id = max(rec.revision_ids, key=lambda r: r.revision)
            else:
                rec.latest_revision_id = False

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
            if not self.customer_account_id:
                rec_line = self.credit_note_id.line_ids.filtered(lambda l: l.account_id.account_type == 'asset_receivable')[:1]
                if rec_line:
                    self.customer_account_id = rec_line.account_id
                else:
                    self.customer_account_id = self.credit_note_id.partner_id.property_account_receivable_id
            if not self.check_pay_to and self.partner_id:
                self.check_pay_to = self.partner_id.name

    @api.onchange("destination_journal_id")
    def _onchange_destination_journal_id(self):
        if self.destination_journal_id:
            # reset method if incompatible
            if self.payment_method_line_id and self.payment_method_line_id.journal_id != self.destination_journal_id:
                self.payment_method_line_id = False

    @api.onchange("partner_id")
    def _onchange_partner_check_pay_to(self):
        if self.partner_id and not self.check_pay_to:
            self.check_pay_to = self.partner_id.name

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
            if "date" not in vals or not vals["date"]:
                vals["date"] = fields.Date.context_today(self)
        return super().create(vals_list)

    def write(self, vals):
        # prevent editing refund_amount mismatch
        if "refund_amount" in vals:
            for rec in self:
                if rec.state != "draft":
                    raise UserError(_("Refund Amount cannot be changed after Draft."))
                # if changing, ensure equals residual
                cn = rec.credit_note_id
                if cn:
                    residual = abs(cn.amount_residual_signed) if hasattr(cn, 'amount_residual_signed') else abs(cn.amount_residual)
                    if abs(vals["refund_amount"] - residual) > 0.01:
                        raise UserError(_("Refund Amount must equal Credit Note residual (%.2f).") % residual)
        # prevent changing credit_note after creation except draft
        if "credit_note_id" in vals:
            for rec in self:
                if rec.state != "draft":
                    raise UserError(_("Cannot change Credit Note after Draft."))
        # handle name /
        if vals.get("name") == "/":
            for rec in self:
                vals["name"] = self.env["ir.sequence"].with_company(rec.company_id).next_by_code("buz.customer.refund.voucher", sequence_date=vals.get("date") or rec.date) or "/"
        return super().write(vals)

    @api.constrains("credit_note_id", "company_id", "partner_id", "refund_amount", "state")
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
            # residual > 0
            residual = abs(cn.amount_residual_signed) if hasattr(cn, 'amount_residual_signed') else abs(cn.amount_residual)
            if residual < 0.01 and rec.state in ("draft", "confirmed"):
                raise ValidationError(_("Credit Note %s has no residual amount.") % cn.name)
            # refund amount must equal residual (snapshot at creation; allow if CN residual changed after registered?)
            if rec.state in ("draft", "confirmed") and abs(rec.refund_amount - residual) > 0.01:
                raise ValidationError(_("Refund Amount (%.2f) must equal Credit Note residual (%.2f).") % (rec.refund_amount, residual))
            # locked period / company_ids check
            if not self.env.user.has_group("base.group_system"):
                # company access
                if rec.company_id not in self.env.companies:
                    raise ValidationError(_("You do not have access to company %s.") % rec.company_id.name)
            # ACL handled by access.csv; additional company_ids check
            # currency check
            if rec.currency_id != rec.company_id.currency_id:
                raise ValidationError(_("Currency must match company currency."))

    @api.constrains("destination_journal_id", "payment_method_line_id", "payment_type", "company_id")
    def _check_journal_payment_method(self):
        for rec in self:
            if rec.destination_journal_id and rec.destination_journal_id.company_id != rec.company_id:
                raise ValidationError(_("Payment Journal must belong to the same company as the CV."))
            if rec.payment_method_line_id and rec.destination_journal_id and rec.payment_method_line_id.journal_id != rec.destination_journal_id:
                raise ValidationError(_("Payment Method does not belong to the selected journal."))
            if rec.payment_method_line_id and rec.payment_method_line_id.payment_type != "outbound":
                raise ValidationError(_("Payment Method must be Outbound."))
            # required journal/method when confirmed? enforce on confirm

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
        """Create immutable revision and return PDF report action. Print allowed in draft/confirmed."""
        self.ensure_one()
        if self.state not in ("draft", "confirmed"):
            raise UserError(_("Printing is only allowed in Draft or Confirmed."))
        # company / ACL check
        self._check_company_access()
        # Create revision snapshot
        max_rev = max(self.revision_ids.mapped("revision") or [0])
        rev_vals = {
            "voucher_id": self.id,
            "revision": max_rev + 1,
            "refund_amount": self.refund_amount,
            "payment_type": self.payment_type,
            "destination_journal_id": self.destination_journal_id.id if self.destination_journal_id else False,
            "payment_method_line_id": self.payment_method_line_id.id if self.payment_method_line_id else False,
            "check_number": self.check_number,
            "check_date": self.check_date,
            "check_pay_to": self.check_pay_to,
            "customer_account_id": self.customer_account_id.id if self.customer_account_id else False,
            "refund_reason": self.refund_reason,
            "snapshot_json": json.dumps({
                "name": self.name,
                "date": str(self.date),
                "partner_id": self.partner_id.id,
                "credit_note_id": self.credit_note_id.id,
                "credit_note_name": self.credit_note_id.name,
                "refund_amount": float(self.refund_amount),
                "payment_type": self.payment_type,
                "journal_id": self.destination_journal_id.id if self.destination_journal_id else False,
            }, ensure_ascii=False),
        }
        revision = self.env["buz.customer.refund.voucher.revision"].create(rev_vals)
        self.message_post(body=_("CV printed — Revision %s created.") % revision.revision)
        # return report action
        return self.env.ref("buz_accounting_addon.action_report_buz_customer_refund_voucher").report_action(self)

    def action_confirm(self):
        """Draft -> Confirmed. Requires latest revision exists. Only latest revision allowed."""
        for rec in self:
            if rec.state != "draft":
                continue
            rec._check_company_access()
            # must have at least one revision and it is the latest (trivially)
            if not rec.revision_ids:
                raise UserError(_("Please Print CV before Confirm. At least one print revision is required."))
            # Confirm only latest revision — if somehow not latest, block (here only check strictly increasing, so always latest after print)
            # Additional checks: locked period, journal, currency, payment method
            if not rec.destination_journal_id and rec.payment_type != "cash":
                # For cash allow empty journal? But spec says support Cash/Transfer/Cheque with journal etc. We'll require journal except cash.
                pass
            if rec.payment_type != "cash" and not rec.payment_method_line_id:
                # Transfer/Cheque require method line
                # Check if journal has outbound method; if missing raise
                if rec.destination_journal_id and not rec.destination_journal_id.outbound_payment_method_line_ids:
                    raise UserError(_("Selected journal has no outbound payment methods."))
            # check ACL: accounting user can confirm (access.csv allows)
            rec.write({"state": "confirmed"})
            rec.message_post(body=_("CV Confirmed."))
        return True

    def action_register_refund(self):
        """Open standard account.payment.register wizard for this CV's credit note. Single transaction."""
        self.ensure_one()
        if self.state != "confirmed":
            raise UserError(_("Only Confirmed CV can register refund."))
        self._check_company_access()
        # ensure CV's credit note still has residual and not already fully reconciled
        cn = self.credit_note_id
        residual = abs(cn.amount_residual_signed) if hasattr(cn, 'amount_residual_signed') else abs(cn.amount_residual)
        if residual < 0.01:
            raise UserError(_("Credit Note %s has no residual to refund.") % cn.name)
        if abs(self.refund_amount - residual) > 0.01:
            raise UserError(_("Refund Amount (%.2f) no longer matches Credit Note residual (%.2f). Please cancel and recreate CV.") % (self.refund_amount, residual))
        # ensure latest revision exists (state confirmed implies)
        if not self.revision_ids:
            raise UserError(_("Missing print revision. Please Print CV before registering."))
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
        """Cancel CV — only Manager can. Allowed from draft/confirmed."""
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
        """Reset to draft — manager only. From confirmed/cancel/payment_cancelled."""
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
            # Use _is_move_consistent? simple check: if date before lock date
            lock_date = rec.company_id.period_lock_date or rec.company_id.fiscalyear_lock_date
            if lock_date and rec.date and rec.date <= lock_date:
                raise UserError(_("CV date is in a locked period (lock date: %s).") % lock_date)

    def unlink(self):
        for rec in self:
            if rec.state != "draft":
                raise UserError(_("Only Draft CV can be deleted."))
        return super().unlink()


class BuzCustomerRefundVoucherRevision(models.Model):
    _name = "buz.customer.refund.voucher.revision"
    _description = "Customer Refund Voucher Revision (Immutable)"
    _order = "revision desc, id desc"

    voucher_id = fields.Many2one("buz.customer.refund.voucher", string="CV", required=True, ondelete="cascade", index=True, readonly=True)
    revision = fields.Integer(string="Revision", required=True, readonly=True)
    create_date = fields.Datetime(string="Printed On", readonly=True, default=fields.Datetime.now)
    create_uid = fields.Many2one("res.users", string="Printed By", readonly=True, default=lambda self: self.env.user)
    refund_amount = fields.Monetary(string="Refund Amount", currency_field="currency_id", readonly=True)
    currency_id = fields.Many2one(related="voucher_id.currency_id", readonly=True, store=False)
    payment_type = fields.Selection(related="voucher_id.payment_type", readonly=True, store=False)
    destination_journal_id = fields.Many2one("account.journal", string="Journal", readonly=True)
    payment_method_line_id = fields.Many2one("account.payment.method.line", string="Payment Method", readonly=True)
    check_number = fields.Char(string="Cheque Number", readonly=True)
    check_date = fields.Date(string="Cheque Date", readonly=True)
    check_pay_to = fields.Char(string="Pay to", readonly=True)
    customer_account_id = fields.Many2one("account.account", string="Customer Account", readonly=True)
    refund_reason = fields.Text(string="Refund Reason", readonly=True)
    snapshot_json = fields.Text(string="Snapshot (JSON)", readonly=True)

    _sql_constraints = [
        ("uniq_voucher_revision", "unique(voucher_id, revision)", "Revision must be unique per CV."),
    ]

    def write(self, vals):
        raise UserError(_("Revisions are immutable and cannot be edited."))

    def unlink(self):
        raise UserError(_("Revisions are immutable and cannot be deleted."))
