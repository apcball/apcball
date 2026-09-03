# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class BuzCustomerRefundPv(models.Model):
    _name = "buz.customer.refund.pv"
    _description = "Customer Refund PV (Phase 1 - Draft only)"
    _order = "date desc, id desc"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _check_company_auto = True

    name = fields.Char(string="Refund PV Number", copy=False, tracking=True, index=True, help="Manual Refund PV number - required before Confirm, used as VOUCHER NO. on report")
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

    # Payment planning fields เนโฌโ€ mirror Vendor PV for layout parity
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

    # Manual refund amount for approval printing (supports partial, e.g. 3,000 of 4,990)
    refund_amount = fields.Monetary(string="Refund Amount", currency_field="currency_id", tracking=True, help="Amount to be refunded as specified by accounting - shown on report")

    # Totals เนโฌโ€ mirror Vendor PV computations for report/layout parity (not changed)
    amount_total_gross = fields.Monetary(string="Total Gross", currency_field="currency_id", compute="_compute_amount_totals", store=True)
    amount_total_wht = fields.Monetary(string="Total WHT", currency_field="currency_id", compute="_compute_amount_totals", store=True)
    amount_total_net = fields.Monetary(string="Total Net", currency_field="currency_id", compute="_compute_amount_totals", store=True)
    amount_total_net_display = fields.Monetary(string="Total Net Display", currency_field="currency_id", compute="_compute_amount_totals")

    # Payment linkage for Register Payment phase (out of scope for Vendor PV)
    payment_ids = fields.Many2many('account.payment', 'buz_customer_refund_pv_payment_rel', 'pv_id', 'payment_id', string='Payments', readonly=True, copy=False)
    payment_count = fields.Integer(string='Payment Count', compute='_compute_payment_count')
    has_active_payment = fields.Boolean(string='Has Active Payment', compute='_compute_has_active_payment')

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

    @api.constrains("name")
    def _check_name_unique(self):
        for rec in self:
            if not rec.name or rec.name in ("/", False, None):
                continue
            dup = self.search([("name", "=", rec.name), ("id", "!=", rec.id)], limit=1)
            if dup:
                raise UserError(_("Refund PV Number '%s' already exists.") % rec.name)

    def write(self, vals):
        if vals.get("name") == "/":
            vals["name"] = self.env["ir.sequence"].next_by_code("buz.customer.refund.pv") or "/"
        # Lock critical fields once posted (including manual name and refund_amount)
        if self and any(rec.state == "posted" for rec in self):
            protected = {
                "name", "partner_id", "credit_note_id", "date", "company_id", "currency_id",
                "payment_type", "destination_journal_id", "payment_method_line_id",
                "bank_free_dis", "other_income_dis", "check_number", "check_date", "check_pay_to",
                "line_ids", "note", "refund_amount",
            }
            if protected.intersection(vals.keys()) and not (set(vals.keys()) <= {"state", "message_follower_ids", "activity_ids", "message_ids"}):
                if not (set(vals.keys()) == {"state"} and vals.get("state") == "posted"):
                    raise UserError(_("Posted Customer Refund PV cannot be edited."))
        return super().write(vals)

    def action_confirm(self):
        """Current phase: Validate and confirm Draft -> Posted. No payment creation / no reconcile."""
        for pv in self:
            if pv.state != "draft":
                raise UserError(_("Only draft Refund PV can be confirmed. Document %s is already %s.") % (pv.name or "", pv.state))
            if not pv.name or pv.name in ("/", False, None, ""):
                raise UserError(_("Refund PV Number is required. Please enter the Refund PV number."))
            dup = self.search([("name", "=", pv.name), ("id", "!=", pv.id)], limit=1)
            if dup:
                raise UserError(_("Refund PV Number '%s' already exists.") % pv.name)
            if not pv.partner_id:
                raise UserError(_("Customer is required."))
            if not pv.date:
                raise UserError(_("PV Date is required."))
            if not pv.credit_note_id:
                raise UserError(_("Customer Credit Note is required."))
            if pv.credit_note_id.move_type != "out_refund":
                raise UserError(_("Credit Note must be a Customer Credit Note (out_refund)."))
            if pv.credit_note_id.state != "posted":
                raise UserError(_("Customer Credit Note must be Posted."))
            if not pv.line_ids:
                raise UserError(_("At least one Refund Line is required."))
            if not pv.refund_amount or pv.refund_amount <= 0:
                raise UserError(_("Refund Amount is required and must be greater than 0."))
            # Amount > 0 checks (gross/net) - keep original formula
            if pv.amount_total_gross <= 0 and pv.amount_total_net <= 0:
                raise UserError(_("Refund amount must be greater than 0."))
            if any(line.amount_to_pay_gross <= 0 for line in pv.line_ids):
                raise UserError(_("Each refund line amount must be greater than 0."))
            # Amount must not exceed residual of credit note
            try:
                residual = abs(pv.credit_note_id.amount_residual_signed) if hasattr(pv.credit_note_id, "amount_residual_signed") else abs(pv.credit_note_id.amount_residual)
            except Exception:
                residual = abs(pv.credit_note_id.amount_total)
            if pv.amount_total_gross - residual > 1e-6:
                raise UserError(_("Refund amount (%.2f) exceeds remaining balance of Credit Note %s (%.2f).") % (pv.amount_total_gross, pv.credit_note_id.name, residual))
            if pv.amount_total_net - residual > 1e-6:
                raise UserError(_("Net refund amount (%.2f) exceeds remaining balance of Credit Note %s (%.2f).") % (pv.amount_total_net, pv.credit_note_id.name, residual))
            if pv.refund_amount - residual > 1e-6:
                raise UserError(_("Refund Amount (%.2f) exceeds remaining balance of Credit Note %s (%.2f).") % (pv.refund_amount, pv.credit_note_id.name, residual))
            # Partial payment: total of all posted PVs for same CN must not exceed CN total (cancelled PVs excluded, cancelled payments not counted as paid but PV still counts)
            other_posted = self.search([('credit_note_id', '=', pv.credit_note_id.id), ('state', '=', 'posted'), ('id', '!=', pv.id)])
            total_other = sum(other_posted.mapped('refund_amount'))
            try:
                cn_total = abs(pv.credit_note_id.amount_total)
            except Exception:
                cn_total = residual
            if total_other + pv.refund_amount - cn_total > 1e-6:
                raise UserError(_("Total Refund Amount (%.2f) for Credit Note %s would exceed its total (%.2f).") % (total_other + pv.refund_amount, pv.credit_note_id.name, cn_total))
        # All validations passed: post the documents
        for pv in self:
            pv.write({"state": "posted"})
            try:
                pv.message_post(body=_("Refund PV confirmed and posted."))
            except Exception:
                pass
        return True

    def unlink(self):
        for pv in self:
            if pv.state == "posted":
                raise UserError(_("Cannot delete a posted Customer Refund PV."))
        return super().unlink()

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

    @api.depends("payment_ids")
    def _compute_payment_count(self):
        for pv in self:
            pv.payment_count = len(pv.payment_ids)

    @api.depends("payment_ids.state")
    def _compute_has_active_payment(self):
        for pv in self:
            pv.has_active_payment = any(p.state != 'cancel' for p in pv.payment_ids)

    def action_view_payments(self):
        self.ensure_one()
        payments = self.payment_ids
        action = {
            "name": _("Payments"),
            "type": "ir.actions.act_window",
            "res_model": "account.payment",
            "view_mode": "tree,form",
            "domain": [("id", "in", payments.ids)],
            "context": {"create": False},
        }
        if len(payments) == 1:
            action.update({"view_mode": "form", "res_id": payments.id})
        return action

    def action_register_refund_payment(self):
        self.ensure_one()
        # Validations per spec for new button on Refund PV
        if self.state != 'posted':
            raise UserError(_("Refund PV must be posted before Register Payment."))
        if not self.credit_note_id:
            raise UserError(_("No Credit Note linked."))
        if self.credit_note_id.move_type != 'out_refund':
            raise UserError(_("Credit Note must be a Customer Credit Note (out_refund)."))
        if self.credit_note_id.state != 'posted':
            raise UserError(_("Credit Note must be Posted."))
        if not self.refund_amount or self.refund_amount <= 0:
            raise UserError(_("Refund Amount must be greater than 0."))
        if self.payment_ids.filtered(lambda p: p.state != 'cancel'):
            raise UserError(_("Payment already registered for Refund PV %s.") % self.name)
        try:
            residual = abs(self.credit_note_id.amount_residual_signed) if hasattr(self.credit_note_id, 'amount_residual_signed') else abs(self.credit_note_id.amount_residual)
        except Exception:
            residual = abs(self.credit_note_id.amount_total)
        if self.refund_amount - residual > 1e-6:
            raise UserError(_("Refund Amount (%.2f) exceeds remaining balance of Credit Note %s (%.2f).") % (self.refund_amount, self.credit_note_id.name, residual))
        # Open standard payment register wizard with forced refund_amount and linking context
        # Only this new button sets buz_customer_refund_pv_id / force_amount, old Credit Note button remains standard
        ctx = dict(self.env.context)
        ctx.update({
            'active_model': 'account.move',
            'active_ids': [self.credit_note_id.id],
            'active_id': self.credit_note_id.id,
            'buz_customer_refund_pv_id': self.id,
            'force_amount': self.refund_amount,
        })
        if self.destination_journal_id:
            ctx['default_journal_id'] = self.destination_journal_id.id
        if self.date:
            ctx['default_payment_date'] = self.date
        if self.payment_method_line_id:
            ctx['default_payment_method_line_id'] = self.payment_method_line_id.id
        return self.credit_note_id.with_context(ctx).action_register_payment()

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

    def get_preview_moves(self):
        """
        Compute simulated journal entry lines for Customer Refund PV report.
        Mirrors Vendor PV (account.payment.voucher.get_preview_moves) but
        adapted for customer receivable accounts. Returns list of dicts:
        { 'code', 'name', 'ref', 'date', 'debit', 'credit' }
        """
        self.ensure_one()
        lines = []
        date = self.date
        voucher_name = self.name
        # Use manual refund_amount for report when specified (supports partial approval), otherwise fall back to line sums
        if self.refund_amount and self.refund_amount > 0:
            total_gross = self.refund_amount
            total_wht = sum(line.wht_amount for line in self.line_ids)
            total_net = total_gross - total_wht
        else:
            total_gross = sum(line.amount_to_pay_gross for line in self.line_ids)
            total_wht = sum(line.wht_amount for line in self.line_ids)
            total_net = sum(line.amount_to_pay_net for line in self.line_ids)
        bank_fee = self.bank_free_dis or 0.0
        other_income = 0.0
        total_disbursement = total_net + bank_fee

        if total_gross > 0:
            if self.line_ids and self.line_ids[0].move_id:
                first_move = self.line_ids[0].move_id
                receivable_line = first_move.line_ids.filtered(lambda l: l.account_id.account_type == 'asset_receivable')[:1]
                account = receivable_line.account_id or first_move.partner_id.property_account_receivable_id
            else:
                account = self.partner_id.property_account_receivable_id or self.env['account.account']
            lines.append({
                'code': account.code if account else '',
                'name': account.name if account else _('Receivable'),
                'ref': voucher_name,
                'date': date,
                'debit': total_gross,
                'credit': 0.0,
            })

        if total_wht > 0:
            wht_account = self.env['account.account'].search([
                ('code', '=', '213102'),
                ('company_id', '=', self.company_id.id)
            ], limit=1)
            if not wht_account:
                wht_account = self.env['account.account'].search([
                    ('code', '=ilike', '%wht%payable%'),
                    ('company_id', '=', self.company_id.id)
                ], limit=1)
            if not wht_account:
                wht_account = self.env['account.account'].search([
                    ('account_type', '=', 'liability_current'),
                    ('company_id', '=', self.company_id.id)
                ], limit=1)
            lines.append({
                'code': wht_account.code if wht_account else '213102',
                'name': wht_account.name if wht_account else 'เน€เธย เน€เธเธ’เน€เธเธเน€เธเธ•เน€เธเธเน€เธเธ‘เน€เธย เน€เธโ€ เน€เธโ€”เน€เธเธ•เน€เธยเน€เธยเน€เธยเน€เธเธ’เน€เธเธเน€เธยเน€เธยเน€เธเธ’เน€เธยเน€เธยเน€เธยเน€เธเธ’เน€เธเธ',
                'ref': voucher_name,
                'date': date,
                'debit': 0.0,
                'credit': total_wht,
            })

        if bank_fee > 0:
            bank_fee_account = self.env['account.account'].search([
                ('code', '=', '533201'),
                ('company_id', '=', self.company_id.id)
            ], limit=1)
            if not bank_fee_account:
                bank_fee_account = self.env['account.account'].search([
                    ('account_type', '=', 'expense'),
                    ('company_id', '=', self.company_id.id)
                ], limit=1)
            lines.append({
                'code': bank_fee_account.code if bank_fee_account else '533201',
                'name': bank_fee_account.name if bank_fee_account else _('Bank Fee Expense'),
                'ref': voucher_name,
                'date': date,
                'debit': bank_fee,
                'credit': 0.0,
            })

        if other_income > 0:
            other_income_account = self.env['account.account'].search([
                ('code', 'in', ['423000', '42300']),
                ('company_id', '=', self.company_id.id)
            ], limit=1)
            if not other_income_account:
                other_income_account = self.env['account.account'].search([
                    ('name', 'ilike', 'เน€เธเธเน€เธเธ’เน€เธเธเน€เธยเน€เธโ€เน€เธยเน€เธเธเน€เธเธ—เน€เธยเน€เธย'),
                    ('company_id', '=', self.company_id.id)
                ], limit=1)
            if not other_income_account:
                other_income_account = self.env['account.account'].search([
                    ('account_type', '=', 'income'),
                    ('company_id', '=', self.company_id.id)
                ], limit=1)
            lines.append({
                'code': other_income_account.code if other_income_account else '423000',
                'name': other_income_account.name if other_income_account else _('เน€เธเธเน€เธเธ’เน€เธเธเน€เธยเน€เธโ€เน€เธยเน€เธเธเน€เธเธ—เน€เธยเน€เธย'),
                'ref': voucher_name,
                'date': date,
                'debit': 0.0,
                'credit': other_income,
            })

        is_check = False
        if self.payment_type == 'check':
            is_check = True
        elif self.payment_method_line_id:
            method_name = self.payment_method_line_id.name or ''
            method_code = getattr(self.payment_method_line_id, 'code', '') or ''
            method_pm_code = ''
            if hasattr(self.payment_method_line_id, 'payment_method_id') and self.payment_method_line_id.payment_method_id:
                method_pm_code = self.payment_method_line_id.payment_method_id.code or ''
            if any(term in method_name.lower() or term in method_code.lower() or term in method_pm_code.lower() for term in ['check', 'cheque']):
                is_check = True

        if is_check:
            check_payable_account = self.env['account.account'].search([
                ('code', '=', '211100'),
                ('company_id', '=', self.company_id.id)
            ], limit=1)
            if not check_payable_account:
                check_payable_account = self.env['account.account'].search([
                    ('name', 'ilike', 'เน€เธโ€ขเน€เธเธ‘เน€เธยเน€เธเธเน€เธโฌเน€เธยเน€เธเธ”เน€เธยเน€เธยเน€เธยเน€เธเธ’เน€เธเธ'),
                    ('company_id', '=', self.company_id.id)
                ], limit=1)
            lines.append({
                'code': check_payable_account.code if check_payable_account else '211100',
                'name': check_payable_account.name if check_payable_account else _('เน€เธโ€ขเน€เธเธ‘เน€เธยเน€เธเธเน€เธโฌเน€เธยเน€เธเธ”เน€เธยเน€เธยเน€เธยเน€เธเธ’เน€เธเธ'),
                'ref': voucher_name,
                'date': date,
                'debit': 0.0,
                'credit': total_disbursement,
            })
        else:
            bank_journal = self.destination_journal_id
            if bank_journal:
                bank_account = bank_journal.default_account_id
                if not bank_account:
                    try:
                        bank_account = bank_journal.outbound_payment_method_line_ids[:1].payment_account_id
                    except Exception:
                        bank_account = self.env['account.account']
                lines.append({
                    'code': bank_account.code if bank_account else '???',
                    'name': bank_account.name if bank_account else bank_journal.name,
                    'ref': voucher_name,
                    'date': date,
                    'debit': 0.0,
                    'credit': total_disbursement,
                })

        return lines


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

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            pv_id = vals.get("pv_id")
            if pv_id:
                pv = self.env["buz.customer.refund.pv"].browse(pv_id)
                if pv.state == "posted":
                    raise UserError(_("Cannot add lines to a posted Customer Refund PV."))
        return super().create(vals_list)

    def write(self, vals):
        if any(line.pv_id.state == "posted" for line in self):
            raise UserError(_("Cannot edit lines of a posted Customer Refund PV."))
        return super().write(vals)

    def unlink(self):
        if any(line.pv_id.state == "posted" for line in self):
            raise UserError(_("Cannot delete lines of a posted Customer Refund PV."))
        return super().unlink()
