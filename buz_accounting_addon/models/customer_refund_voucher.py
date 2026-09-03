# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError, AccessError
import re
import json
import logging

_logger = logging.getLogger(__name__)

CV_NUMBER_RE = re.compile(r"^CV/(\d{4})/(\d{4})$")


class BuzCustomerRefundVoucher(models.Model):
    _name = "buz.customer.refund.voucher"
    _description = "Customer Refund PV"
    _order = "date desc, id desc"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _check_company_auto = True

    name = fields.Char(string="CV Number", readonly=True, copy=False, default="/", tracking=True)
    date = fields.Date(string="Voucher Date", default=fields.Date.context_today, required=True, tracking=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, tracking=True)
    currency_id = fields.Many2one("res.currency", related="company_id.currency_id", readonly=True)
    partner_id = fields.Many2one("res.partner", string="Customer", required=True, domain=[("customer_rank", ">", 0)], tracking=True, check_company=True)
    credit_note_id = fields.Many2one("account.move", string="Customer Credit Note", required=True, domain="[('move_type','=','out_refund'),('state','=','posted')]", check_company=True, index=True, tracking=True)
    credit_note_amount = fields.Monetary(string="Original Credit Amount", currency_field="currency_id", compute="_compute_credit_amounts", store=True, readonly=True)
    amount_residual_before = fields.Monetary(string="Residual Before", currency_field="currency_id", compute="_compute_credit_amounts", store=True, readonly=True)
    # snapshot stored at confirm
    residual_before_snapshot = fields.Monetary(string="Residual Snapshot", currency_field="currency_id", readonly=True, copy=False)
    credit_amount_snapshot = fields.Monetary(string="Credit Amount Snapshot", currency_field="currency_id", readonly=True, copy=False)
    refund_amount = fields.Monetary(string="Refund Amount", currency_field="currency_id", required=True, tracking=True)
    difference_handling = fields.Selection([("keep_open", "Keep Open"), ("writeoff", "Write Off")], string="Difference Handling", default="keep_open", required=True, tracking=True)
    difference_amount = fields.Monetary(string="Difference Amount", currency_field="currency_id", compute="_compute_difference", store=True, readonly=True)
    writeoff_account_id = fields.Many2one("account.account", string="Write-off Account", check_company=True, tracking=True)
    writeoff_reason = fields.Text(string="Write-off Reason", tracking=True)
    payment_type = fields.Selection([("cash", "Cash"), ("transfer", "Transfer"), ("check", "Check")], string="Payment Type", default="transfer", required=True, tracking=True)
    planned_payment_date = fields.Date(string="Planned Payment Date", default=fields.Date.context_today, tracking=True)
    destination_journal_id = fields.Many2one("account.journal", string="Payment Journal", domain="[('type','in',('bank','cash')),('company_id','=',company_id)]", tracking=True, check_company=True)
    payment_method_line_id = fields.Many2one("account.payment.method.line", string="Payment Method", domain="[('payment_type','=','outbound'),('journal_id','=',destination_journal_id)]", tracking=True)
    check_number = fields.Char(string="Cheque Number", tracking=True)
    check_date = fields.Date(string="Cheque Date", tracking=True)
    check_pay_to = fields.Char(string="Pay to", tracking=True)
    note = fields.Text(string="Note")
    state = fields.Selection([("draft", "Draft"), ("confirmed", "Confirmed"), ("cancel", "Cancelled")], default="draft", tracking=True, copy=False)
    workflow_state = fields.Selection([
        ("draft", "Draft"),
        ("confirmed", "Confirmed"),
        ("in_payment", "In Payment"),
        ("partially_refunded", "Partially Refunded"),
        ("paid", "Paid"),
        ("exception", "Exception"),
        ("reversed", "Reversed"),
        ("cancelled", "Cancelled"),
    ], string="Workflow State", compute="_compute_workflow_state", store=True)
    payment_ids = fields.One2many("account.payment", "buz_customer_refund_voucher_id", string="Payments", readonly=True, copy=False)
    payment_count = fields.Integer(compute="_compute_payment_count", string="Payments")
    printed_at = fields.Datetime(string="Printed At", readonly=True, copy=False)
    printed_by = fields.Many2one("res.users", string="Printed By", readonly=True, copy=False)
    confirmation_snapshot = fields.Text(string="Confirmation Snapshot", readonly=True, copy=False)
    confirmed_by = fields.Many2one("res.users", string="Confirmed By", readonly=True, copy=False)
    confirmed_date = fields.Datetime(string="Confirmed Date", readonly=True, copy=False)
    registered_by = fields.Many2one("res.users", string="Registered By", readonly=True, copy=False)
    registered_date = fields.Datetime(string="Registered Date", readonly=True, copy=False)
    # attachment field placeholder - use ir.attachment via message?

    _sql_constraints = [
        ("name_company_uniq", "unique(name, company_id)", "CV Number must be unique per company."),
    ]

    @api.depends("credit_note_id.amount_total_signed", "credit_note_id.amount_total", "credit_note_id.amount_residual_signed", "credit_note_id.amount_residual")
    def _compute_credit_amounts(self):
        for rec in self:
            cn = rec.credit_note_id
            if cn:
                # amount_total_signed for out_refund is negative, use absolute
                if hasattr(cn, "amount_total_signed"):
                    rec.credit_note_amount = abs(cn.amount_total_signed)
                else:
                    rec.credit_note_amount = abs(cn.amount_total)
                if hasattr(cn, "amount_residual_signed"):
                    rec.amount_residual_before = abs(cn.amount_residual_signed)
                else:
                    rec.amount_residual_before = abs(cn.amount_residual)
            else:
                rec.credit_note_amount = 0
                rec.amount_residual_before = 0

    @api.depends("amount_residual_before", "refund_amount", "residual_before_snapshot", "state")
    def _compute_difference(self):
        for rec in self:
            base = rec.residual_before_snapshot if rec.state != "draft" and rec.residual_before_snapshot else rec.amount_residual_before
            # if full refund, diff 0 regardless of handling
            if rec.currency_id:
                base = rec.currency_id.round(base)
                refund = rec.currency_id.round(rec.refund_amount or 0)
            else:
                refund = rec.refund_amount or 0
            diff = max(0, base - refund) if base else 0
            # if refund equals residual, diff 0
            if abs(base - refund) < 0.0001:
                diff = 0
            rec.difference_amount = diff

    @api.depends("payment_ids", "payment_ids.state", "payment_ids.move_id", "state", "payment_type", "difference_handling")
    def _compute_payment_count(self):
        for rec in self:
            rec.payment_count = len(rec.payment_ids)

    @api.depends("state", "payment_ids.state", "payment_ids.is_matched", "payment_ids.move_id", "payment_ids.reconciled_bill_ids", "payment_ids.reconciled_bills_count", "credit_note_id.amount_residual", "credit_note_id.amount_residual_signed", "payment_type", "difference_handling")
    def _compute_workflow_state(self):
        for rec in self:
            if rec.state == "cancel":
                rec.workflow_state = "cancelled"
                continue
            if rec.state == "draft":
                rec.workflow_state = "draft"
                continue
            # confirmed state but check payments
            payments = rec.payment_ids
            if not payments:
                # check if reversed? No payments => confirmed
                rec.workflow_state = "confirmed"
                continue
            # filter posted payments
            posted = payments.filtered(lambda p: p.state == "posted")
            cancelled = payments.filtered(lambda p: p.state == "cancel")
            draft_pay = payments.filtered(lambda p: p.state == "draft")
            # If any draft payment -> exception (reset to draft scenario)
            if draft_pay:
                rec.workflow_state = "exception"
                continue
            # If all cancelled -> reversed if residual restored
            if posted and len(posted) == 0 and cancelled:
                # check if credit note residual restored
                cn_residual = rec._get_cn_residual()
                base = rec.residual_before_snapshot or rec.amount_residual_before
                # if residual close to original before, considered reversed
                # compare with snapshot credit amount?
                # simplified: if cn residual >= snapshot residual minus small epsilon -> reversed
                if cn_residual and base and abs(cn_residual - base) < 0.01:
                    rec.workflow_state = "reversed"
                elif cn_residual and cn_residual > 0:
                    # partial reversed? treat as reversed
                    rec.workflow_state = "reversed"
                else:
                    rec.workflow_state = "exception"
                continue
            if not posted:
                # no posted but have cancelled only
                if cancelled:
                    rec.workflow_state = "reversed"
                else:
                    rec.workflow_state = "exception"
                continue
            # Check reconciliation with credit note
            # If payment not reconciled with credit note -> exception, except bank unreconcile case
            # Evaluate bank reconciliation for transfer/check
            # Simplified: check if credit note residual indicates paid
            cn_residual = rec._get_cn_residual()
            is_bank_reconciled = rec._is_bank_reconciled()
            # Unreconcile detection: if payment is posted but not reconciled with CN and CN residual not zero -> exception
            # We can detect via partial reconcile existence
            is_reconciled_with_cn = rec._is_reconciled_with_cn()
            if not is_reconciled_with_cn:
                # If bank unreconcile case: payment still reconciled with CN but bank not reconciled => should be in_payment not exception
                # But if not reconciled with CN at all => exception
                # Check if CN residual indicates still outstanding but payment exists
                # If payment exists and CN residual >0 and diff handling keep_open expects partial, might still be partially_refunded
                # Need to distinguish: bank unreconcile vs payment-CN unreconcile
                # For now, if not reconciled with CN -> exception
                rec.workflow_state = "exception"
                continue
            # At this point payment is posted and reconciled with CN
            if rec.payment_type in ("transfer", "check") and not is_bank_reconciled:
                rec.workflow_state = "in_payment"
                continue
            # Check if CN still has residual (keep_open)
            if cn_residual and cn_residual > 0.005:
                # if keep_open expected, then partially_refunded
                if rec.difference_amount > 0.005:
                    rec.workflow_state = "partially_refunded"
                else:
                    # should be paid but still residual => exception
                    rec.workflow_state = "exception"
                continue
            else:
                # CN closed
                rec.workflow_state = "paid"
                continue

    def _get_cn_residual(self):
        self.ensure_one()
        cn = self.credit_note_id
        if not cn:
            return 0
        if hasattr(cn, "amount_residual_signed"):
            return abs(cn.amount_residual_signed)
        return abs(cn.amount_residual)

    def _is_reconciled_with_cn(self):
        self.ensure_one()
        # Check if payment move lines are reconciled with credit note receivable lines
        if not self.payment_ids:
            return False
        cn = self.credit_note_id
        if not cn:
            return False
        # Find receivable lines of CN
        cn_lines = cn.line_ids.filtered(lambda l: l.account_id.account_type == "asset_receivable")
        if not cn_lines:
            return False
        # Check if any cn line is reconciled with payment lines
        for pay in self.payment_ids.filtered(lambda p: p.state == "posted"):
            pay_lines = pay.move_id.line_ids.filtered(lambda l: l.account_id.account_type in ("asset_receivable", "liability_payable"))
            # Check partial reconcile between cn lines and pay lines
            for cn_line in cn_lines:
                # matched credit/debit
                if cn_line.matched_debit_ids or cn_line.matched_credit_ids:
                    # check if any partial involves pay line
                    for partial in cn_line.matched_debit_ids | cn_line.matched_credit_ids:
                        if partial.debit_move_id in pay_lines or partial.credit_move_id in pay_lines:
                            return True
                # also check pay line reconciled
                for pl in pay_lines:
                    if pl.matched_debit_ids or pl.matched_credit_ids:
                        for partial in pl.matched_debit_ids | pl.matched_credit_ids:
                            if partial.debit_move_id in cn_lines or partial.credit_move_id in cn_lines:
                                return True
        return False

    def _is_bank_reconciled(self):
        self.ensure_one()
        # For cash, always bank reconciled immediately
        if self.payment_type == "cash":
            return True
        # For transfer/check, check if payment is matched with bank statement
        for pay in self.payment_ids.filtered(lambda p: p.state == "posted"):
            # Odoo 17: payment has is_matched flag for bank reconciliation
            if hasattr(pay, "is_matched"):
                if pay.is_matched:
                    return True
            # fallback: check statement_line_ids
            if hasattr(pay, "statement_line_ids") and pay.statement_line_ids:
                return True
            # check if move line reconciled with liquidity beyond receivable
            # if payment move has more than one reconcile (receivable + liquidity) maybe bank not needed
            # Simplified: if payment move lines are fully reconciled and amount zero residual, consider bank done for test
            # For now return False if not matched, to enforce in_payment
            # But to allow tests to pass for transfer without statement, we treat as not reconciled
            pass
        return False

    @api.onchange("credit_note_id")
    def _onchange_credit_note_id(self):
        if self.credit_note_id:
            if self.company_id and self.credit_note_id.company_id != self.company_id:
                self.company_id = self.credit_note_id.company_id
            self.partner_id = self.credit_note_id.partner_id
            residual = self._get_cn_residual() if self.credit_note_id else 0
            # currency rounding
            if self.currency_id:
                residual = self.currency_id.round(residual)
            self.refund_amount = residual
            if not self.check_pay_to and self.partner_id:
                self.check_pay_to = self.partner_id.name
            # default planned date
            if not self.planned_payment_date:
                self.planned_payment_date = fields.Date.context_today(self)

    @api.onchange("destination_journal_id")
    def _onchange_destination_journal_id(self):
        if self.destination_journal_id and self.payment_method_line_id and self.payment_method_line_id.journal_id != self.destination_journal_id:
            self.payment_method_line_id = False

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        if self.partner_id and not self.check_pay_to:
            self.check_pay_to = self.partner_id.name

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # security: creation must come from credit note context via move or via direct create with credit_note
            # enforce server side: credit_note must be posted out_refund with residual
            cn_id = vals.get("credit_note_id")
            if not cn_id:
                raise ValidationError(_("Customer Refund PV must be created from a Posted Customer Credit Note."))
            cn = self.env["account.move"].browse(cn_id)
            # check access
            cn.check_access_rights("read")
            cn.check_access_rule("read")
            if cn.move_type != "out_refund" or cn.state != "posted":
                raise ValidationError(_("Credit Note must be Posted out_refund."))
            if hasattr(cn, "amount_residual_signed"):
                residual = abs(cn.amount_residual_signed)
            else:
                residual = abs(cn.amount_residual)
            if residual < 0.01:
                raise ValidationError(_("Credit Note has no residual to refund."))
            # active uniqueness check with lock
            self.env.cr.execute("SELECT id FROM account_move WHERE id=%s FOR UPDATE", (cn_id,))
            active = self.search([("credit_note_id", "=", cn_id), ("state", "in", ["draft", "confirmed", "in_payment", "exception"])], limit=1)
            # workflow_state not stored as state, so check state in draft/confirmed and workflow_state via logic?
            # Use state for active: draft, confirmed are active; also workflow in_payment/exception considered active
            # Search for active via state draft/confirmed and also check workflow not terminal
            # For simplicity check state draft/confirmed
            # Also need to consider workflow_state but we can search payment-based after
            # Do broader search for any voucher with same CN not cancelled/reversed/paid/partially
            # Use compute? fallback: check existing vouchers that are not cancel/paid/partially/reversed
            # We search for vouchers with same CN where state != cancel and workflow not in (paid, partially_refunded, reversed, cancelled)
            # Since workflow is compute, we manually filter
            # Simpler: enforce only one draft/confirmed at a time
            if active:
                # check workflow of active
                # A posted payment that is already reconciled with the CN may
                # leave the CV in ``in_payment`` while waiting for bank
                # reconciliation.  The remaining CN balance can safely be
                # refunded by a subsequent CV in that case.
                if active.workflow_state in ("draft", "confirmed", "exception") or (
                    active.workflow_state == "in_payment"
                    and not active._is_reconciled_with_cn()
                ):
                    raise ValidationError(_("An active Refund PV (%s) already exists for Credit Note %s.") % (active.name, cn.name))
            # generate sequence
            if vals.get("name", "/") in ("/", False, None):
                company = self.env["res.company"].browse(vals.get("company_id")) if vals.get("company_id") else self.env.company
                seq_date = vals.get("date") or fields.Date.context_today(self)
                seq = self.env["ir.sequence"].with_company(company).next_by_code("buz.customer.refund.voucher", sequence_date=seq_date) or "/"
                vals["name"] = seq
            if "date" not in vals or not vals["date"]:
                vals["date"] = fields.Date.context_today(self)
            if not vals.get("planned_payment_date"):
                vals["planned_payment_date"] = vals.get("date")
            # default partner from CN if not set
            if not vals.get("partner_id"):
                vals["partner_id"] = cn.partner_id.id
            if not vals.get("company_id"):
                vals["company_id"] = cn.company_id.id
            # currency check
            comp = self.env["res.company"].browse(vals.get("company_id")) if vals.get("company_id") else self.env.company
            # refund_amount must be provided and validate
            refund = vals.get("refund_amount")
            if refund is None:
                vals["refund_amount"] = residual
                refund = residual
            # validate refund amount >0 and <= residual
            # Use company currency rounding
            curr = comp.currency_id
            if curr:
                refund = curr.round(refund)
                residual_rounded = curr.round(residual)
            else:
                residual_rounded = residual
            if refund <= 0:
                raise ValidationError(_("Refund amount must be greater than 0."))
            if refund - residual_rounded > 0.01:
                raise ValidationError(_("Refund amount exceeds Credit Note residual."))
            # difference handling: if refund == residual, diff 0, handling irrelevant
            # validate writeoff fields
            handling = vals.get("difference_handling", "keep_open")
            if handling == "writeoff":
                if refund and abs(refund - residual_rounded) < 0.01:
                    # no diff, but allow
                    pass
                else:
                    if not vals.get("writeoff_account_id"):
                        raise ValidationError(_("Write-off account is required for Write Off."))
                    if not vals.get("writeoff_reason"):
                        raise ValidationError(_("Write-off reason is required."))
            # also check company active etc is done in constraints
        return super().create(vals_list)

    def write(self, vals):
        # restrict name editing
        if "name" in vals:
            for rec in self:
                if rec.state != "draft":
                    raise UserError(_("CV Number can only be edited in Draft."))
                if not self.env.user.has_group("account.group_account_manager"):
                    raise AccessError(_("Only Accounting Manager can edit CV Number."))
                new_name = vals["name"]
                if not CV_NUMBER_RE.match(new_name):
                    raise ValidationError(_("CV Number must be format CV/YYYY/NNNN."))
                # year must match date
                year_in_name = new_name.split("/")[1]
                voucher_year = str(rec.date.year if rec.date else fields.Date.context_today(self).year)
                target_date = vals.get("date", rec.date)
                if target_date:
                    voucher_year = str(target_date.year)
                if year_in_name != voucher_year:
                    raise ValidationError(_("Year in CV Number must match Voucher Date year."))
                # duplicate check
                dup = self.search([("name", "=", new_name), ("company_id", "=", rec.company_id.id), ("id", "!=", rec.id)], limit=1)
                if dup:
                    raise ValidationError(_("CV Number already exists in this company."))
                # sequence advancing: if new number >= next sequence, advance
                seq = self.env["ir.sequence"].search([("code", "=", "buz.customer.refund.voucher"), ("company_id", "=", rec.company_id.id)], limit=1)
                if not seq:
                    seq = self.env["ir.sequence"].search([("code", "=", "buz.customer.refund.voucher"), ("company_id", "=", False)], limit=1)
                if seq:
                    # get date range for year
                    seq_date = target_date or rec.date
                    # try to check number value
                    try:
                        new_seq_num = int(new_name.split("/")[-1])
                        # get current sequence number (next number)
                        # For date_range sequences, need to check ir.sequence.date_range
                        seq_to_check = seq
                        # find date_range
                        dr = self.env["ir.sequence.date_range"].search([("sequence_id", "=", seq.id), ("date_from", "<=", seq_date), ("date_to", ">=", seq_date)], limit=1)
                        if dr:
                            cur = dr.number_next_actual
                            if new_seq_num >= cur:
                                dr.sudo().write({"number_next_actual": new_seq_num + 1})
                        else:
                            if new_seq_num >= (seq.number_next_actual or 0):
                                seq.sudo().write({"number_next_actual": new_seq_num + 1})
                    except Exception:
                        pass
        # restrict fields after confirm
        locked_fields = ["credit_note_id", "partner_id", "company_id", "refund_amount", "difference_handling", "writeoff_account_id", "writeoff_reason", "payment_type", "destination_journal_id", "payment_method_line_id", "planned_payment_date", "check_number", "check_date", "check_pay_to"]
        if any(f in vals for f in locked_fields):
            for rec in self:
                if rec.state == "confirmed":
                    # after confirm locked
                    raise UserError(_("Cannot modify confirmed voucher fields. Cancel and recreate."))
                if rec.state == "cancel":
                    raise UserError(_("Cannot modify cancelled voucher."))
        # date change after numbering: must stay within same year
        if "date" in vals:
            for rec in self:
                if rec.name and rec.name != "/":
                    m = CV_NUMBER_RE.match(rec.name)
                    if m:
                        year_in_name = m.group(1)
                        new_date = vals["date"]
                        if new_date:
                            from datetime import date as dt_date
                            if isinstance(new_date, str):
                                new_date = fields.Date.from_string(new_date)
                            if str(new_date.year) != year_in_name:
                                raise ValidationError(_("Cannot change Voucher Date to different year after numbering. Cancel and recreate."))
                        # lock date check
                        lock = rec.company_id.period_lock_date or rec.company_id.fiscalyear_lock_date
                        if lock and new_date and new_date <= lock:
                            raise ValidationError(_("Voucher date is in locked period."))
        return super().write(vals)

    def unlink(self):
        raise UserError(_("Customer Refund PV cannot be deleted. Use Cancel/Reversal."))

    @api.constrains("refund_amount", "difference_handling", "writeoff_account_id", "writeoff_reason", "company_id")
    def _check_amounts(self):
        for rec in self:
            curr = rec.currency_id or rec.company_id.currency_id
            refund = rec.refund_amount or 0
            if curr:
                refund = curr.round(refund)
            if refund <= 0:
                raise ValidationError(_("Refund amount must be greater than 0."))
            base = rec.residual_before_snapshot if rec.state != "draft" and rec.residual_before_snapshot else rec.amount_residual_before
            if curr:
                base = curr.round(base) if base else 0
            if base and refund - base > 0.01:
                raise ValidationError(_("Refund amount exceeds Credit Note residual."))
            # currency must be company currency (single currency)
            if rec.currency_id != rec.company_id.currency_id:
                raise ValidationError(_("Only company currency is allowed."))
            if rec.difference_handling == "writeoff":
                # if full refund, not required but if partial diff >0 require account/reason
                if rec.difference_amount > 0.005:
                    if not rec.writeoff_account_id:
                        raise ValidationError(_("Write-off account is required."))
                    if not rec.writeoff_reason:
                        raise ValidationError(_("Write-off reason is required."))
                    acc = rec.writeoff_account_id
                    if acc.company_id != rec.company_id:
                        raise ValidationError(_("Write-off account must belong to same company."))
                    # Odoo 17 ใช้ `deprecated` สำหรับปิดการใช้งานบัญชี และไม่มี field `active`
                    if acc.deprecated:
                        raise ValidationError(_("Write-off account must not be deprecated."))
                    if acc.account_type not in ("income", "income_other"):
                        raise ValidationError(_("Write-off account must be income type."))

    @api.constrains("destination_journal_id", "payment_method_line_id", "company_id")
    def _check_journal(self):
        for rec in self:
            if rec.destination_journal_id and rec.destination_journal_id.company_id != rec.company_id:
                raise ValidationError(_("Journal must belong to same company."))
            if rec.payment_method_line_id:
                if rec.payment_method_line_id.journal_id != rec.destination_journal_id:
                    raise ValidationError(_("Payment method does not belong to journal."))
                if rec.payment_method_line_id.payment_type != "outbound":
                    raise ValidationError(_("Payment method must be outbound."))

    @api.constrains("credit_note_id", "partner_id", "company_id")
    def _check_credit_note(self):
        for rec in self:
            cn = rec.credit_note_id
            if not cn:
                continue
            if cn.move_type != "out_refund":
                raise ValidationError(_("Credit Note must be out_refund."))
            if cn.state != "posted":
                raise ValidationError(_("Credit Note must be posted."))
            if cn.company_id != rec.company_id:
                raise ValidationError(_("Credit Note company mismatch."))
            if cn.partner_id.commercial_partner_id != rec.partner_id.commercial_partner_id and cn.partner_id != rec.partner_id:
                # allow commercial partner match? spec says customer/commercial partner must match
                if cn.partner_id.commercial_partner_id != rec.partner_id.commercial_partner_id:
                    raise ValidationError(_("Customer must match Credit Note."))
            if rec.company_id not in self.env.companies and not self.env.su:
                # company access via record rule, but also check
                pass

    def action_confirm(self):
        for rec in self:
            if rec.state != "draft":
                continue
            # check access
            if not self.env.user.has_group("account.group_account_invoice"):
                raise AccessError(_("Only Accounting Users can confirm."))
            # lock row
            self.env.cr.execute("SELECT id FROM account_move WHERE id=%s FOR UPDATE", (rec.credit_note_id.id,))
            # re-validate residual and active
            cn = rec.credit_note_id
            cn_residual = abs(cn.amount_residual_signed) if hasattr(cn, "amount_residual_signed") else abs(cn.amount_residual)
            if cn_residual < 0.01:
                raise ValidationError(_("Credit Note has no residual."))
            # check duplicate active
            others = self.search([("credit_note_id", "=", cn.id), ("id", "!=", rec.id), ("state", "in", ["draft", "confirmed"])], limit=1)
            if others and (
                others.workflow_state in ("draft", "confirmed", "exception")
                or (
                    others.workflow_state == "in_payment"
                    and not others._is_reconciled_with_cn()
                )
            ):
                raise ValidationError(_("Active voucher %s exists for this credit note.") % others.name)
            # validate fields before confirm
            rec._check_amounts()
            # snapshot
            vals = {
                "state": "confirmed",
                "residual_before_snapshot": cn_residual,
                "credit_amount_snapshot": abs(cn.amount_total_signed) if hasattr(cn, "amount_total_signed") else abs(cn.amount_total),
                "confirmed_by": self.env.user.id,
                "confirmed_date": fields.Datetime.now(),
                "confirmation_snapshot": json.dumps({
                    "name": rec.name,
                    "date": str(rec.date),
                    "credit_note": cn.name,
                    "partner_id": rec.partner_id.id,
                    "refund_amount": float(rec.refund_amount),
                    "difference_handling": rec.difference_handling,
                    "difference_amount": float(rec.difference_amount),
                    "writeoff_account_id": rec.writeoff_account_id.id if rec.writeoff_account_id else False,
                    "writeoff_reason": rec.writeoff_reason,
                    "payment_type": rec.payment_type,
                    "planned_payment_date": str(rec.planned_payment_date) if rec.planned_payment_date else False,
                    "destination_journal_id": rec.destination_journal_id.id if rec.destination_journal_id else False,
                    "payment_method_line_id": rec.payment_method_line_id.id if rec.payment_method_line_id else False,
                    "check_number": rec.check_number,
                    "check_date": str(rec.check_date) if rec.check_date else False,
                    "check_pay_to": rec.check_pay_to,
                }, ensure_ascii=False)
            }
            rec.write(vals)
            rec.message_post(body=_("Customer Refund PV Confirmed by %s. Amount: %s") % (self.env.user.name, rec.refund_amount))
        return True

    def action_cancel(self):
        for rec in self:
            if rec.state == "cancel":
                continue
            if rec.state not in ("draft", "confirmed"):
                raise UserError(_("Only Draft/Confirmed can be cancelled. In Payment/Paid must reverse payment first."))
            if rec.payment_ids:
                raise UserError(_("Cannot cancel voucher with payments. Reverse payments first."))
            if not self.env.user.has_group("account.group_account_manager"):
                raise AccessError(_("Only Accounting Manager can cancel."))
            rec.write({"state": "cancel"})
            rec.message_post(body=_("Customer Refund PV Cancelled by %s") % self.env.user.name)
        return True

    def action_print(self):
        self.ensure_one()
        if self.workflow_state not in ("confirmed", "in_payment", "partially_refunded", "paid"):
            raise UserError(_("Printing allowed only for Confirmed, In Payment, Partially Refunded, Paid."))
        # access check done in report adapter too
        self.write({"printed_at": fields.Datetime.now(), "printed_by": self.env.user.id})
        self.message_post(body=_("Customer Refund PV printed by %s at %s") % (self.env.user.name, self.printed_at))
        return self.env.ref("buz_accounting_addon.action_report_customer_refund_pv").report_action(self)

    def action_register_payment(self):
        self.ensure_one()
        if self.state != "confirmed":
            raise UserError(_("Only Confirmed can register payment."))
        # open wrapper wizard
        return {
            "name": _("Register Refund Payment"),
            "type": "ir.actions.act_window",
            "res_model": "buz.customer.refund.payment.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_voucher_id": self.id, "default_payment_date": fields.Date.context_today(self)},
        }

    def action_open_payments(self):
        self.ensure_one()
        return {
            "name": _("Payments"),
            "type": "ir.actions.act_window",
            "res_model": "account.payment",
            "view_mode": "tree,form",
            "domain": [("buz_customer_refund_voucher_id", "=", self.id)],
            "context": {"create": False},
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

    def get_preview_moves(self):
        self.ensure_one()
        # Proposed journal entry preview
        lines = []
        date = self.date
        name = self.name
        refund = self.refund_amount
        diff = self.difference_amount
        # Find receivable account from credit note
        cn = self.credit_note_id
        receivable = cn.line_ids.filtered(lambda l: l.account_id.account_type == "asset_receivable")[:1].account_id if cn else self.env["account.account"]
        if not receivable:
            receivable = self.partner_id.property_account_receivable_id
        # Journal account for payment (bank/cash)
        pay_account = self.destination_journal_id.default_account_id if self.destination_journal_id else self.env["account.account"]
        if not pay_account and self.destination_journal_id:
            pay_account = self.destination_journal_id.outbound_payment_method_line_ids[:1].payment_account_id
        # Dr Receivable
        total_dr = refund + diff if self.difference_handling == "writeoff" else refund
        if receivable:
            lines.append({"code": receivable.code, "name": receivable.name, "ref": name, "date": date, "debit": total_dr, "credit": 0.0})
        # Cr Pay account
        if pay_account:
            lines.append({"code": pay_account.code or "???", "name": pay_account.name or (self.destination_journal_id.name if self.destination_journal_id else "Bank"), "ref": name, "date": date, "debit": 0.0, "credit": refund})
        # Cr Write-off
        if self.difference_handling == "writeoff" and diff > 0 and self.writeoff_account_id:
            lines.append({"code": self.writeoff_account_id.code, "name": self.writeoff_account_id.name, "ref": name, "date": date, "debit": 0.0, "credit": diff})
        return lines

    def _check_company_access(self):
        for rec in self:
            if rec.company_id not in self.env.companies:
                raise AccessError(_("Access denied for company %s") % rec.company_id.name)
