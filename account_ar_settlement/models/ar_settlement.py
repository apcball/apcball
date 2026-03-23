# -*- coding: utf-8 -*-

import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class ArSettlement(models.Model):
    _name = 'ar.settlement'
    _description = 'AR Settlement'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'payment_date desc, name desc'

    # ── Header ──────────────────────────────────────────────────────────
    name = fields.Char(
        string='Reference', required=True, default='New', copy=False,
        tracking=True,
    )
    partner_id = fields.Many2one(
        'res.partner', string='Customer', required=True,
        tracking=True, states={'confirmed': [('readonly', True)]},
    )
    vat_group = fields.Char(
        string='VAT Group', compute='_compute_vat_group', store=True,
        help='Invoices from partners sharing this VAT will be loaded.',
    )
    trade_channel = fields.Selection([
        ('shopee', 'Shopee'),
        ('lazada', 'Lazada'),
        ('nocnoc', 'Noc Noc'),
        ('tiktok', 'Tiktok'),
        ('spx', 'SPX'),
        ('online_line_fb', 'ONLINE / Line + Facebook'),
        ('offline_mogen_outlet', 'OFFLINE / Mogen Outlet'),
        ('after_sale_service', 'After Sale Service'),
        ('installation_service', 'Installation Service'),
        ('own_channel_cdc', 'Own Channel (CDC)'),
        ('other', 'Other'),
    ], string='Trade Channel',
        states={'confirmed': [('readonly', True)]},
    )

    payment_date = fields.Date(
        string='Payment Date', required=True,
        default=fields.Date.context_today,
        states={'confirmed': [('readonly', True)]},
        tracking=True,
    )
    journal_id = fields.Many2one(
        'account.journal', string='Payment Journal', required=True,
        domain=[('type', 'in', ['bank', 'cash'])],
        states={'confirmed': [('readonly', True)]},
    )
    currency_id = fields.Many2one(
        'res.currency', string='Currency', required=True,
        default=lambda self: self.env.company.currency_id,
        states={'confirmed': [('readonly', True)]},
    )
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company,
    )

    # ── Amounts ─────────────────────────────────────────────────────────
    amount_received = fields.Monetary(
        string='Amount Received', required=True,
        currency_field='currency_id',
        states={'confirmed': [('readonly', True)]},
        tracking=True,
    )
    bank_fee = fields.Monetary(
        string='Bank Fee', currency_field='currency_id',
        states={'confirmed': [('readonly', True)]},
    )
    bank_fee_account_id = fields.Many2one(
        'account.account', string='Bank Fee Account',
        help='Expense account for the bank fee.',
        states={'confirmed': [('readonly', True)]},
    )

    # ── Filters ─────────────────────────────────────────────────────────
    filter_date_from = fields.Date(
        string='From Date',
        states={'confirmed': [('readonly', True)]},
    )
    filter_date_to = fields.Date(
        string='To Date',
        states={'confirmed': [('readonly', True)]},
    )

    # ── Lines ───────────────────────────────────────────────────────────
    line_ids = fields.One2many(
        'ar.settlement.line', 'settlement_id', string='Invoice Allocations',
        states={'confirmed': [('readonly', True)]},
    )
    credit_line_ids = fields.One2many(
        'ar.settlement.credit.line', 'settlement_id', string='Credit Notes',
        states={'confirmed': [('readonly', True)]},
    )

    # ── Computed totals ─────────────────────────────────────────────────
    credit_used = fields.Monetary(
        string='Credit Used', compute='_compute_totals', store=True,
        currency_field='currency_id',
    )
    allocated_amount = fields.Monetary(
        string='Allocated Amount', compute='_compute_totals', store=True,
        currency_field='currency_id',
    )
    total_available = fields.Monetary(
        string='Total Available', compute='_compute_totals', store=True,
        currency_field='currency_id',
        help='Amount Received − Bank Fee + Credit Used',
    )
    remaining_amount = fields.Monetary(
        string='Remaining Balance', compute='_compute_totals', store=True,
        currency_field='currency_id',
    )
    difference_amount = fields.Monetary(
        string='Difference Amount', compute='_compute_totals', store=True,
        currency_field='currency_id',
        help='Positive = overpayment, Negative = underpayment',
    )

    # ── Difference handling ─────────────────────────────────────────────
    difference_handling = fields.Selection([
        ('credit', 'Customer Credit'),
        ('write_off', 'Write Off'),
        ('partial', 'Partial Payment'),
    ], string='Difference Handling', default='write_off',
        states={'confirmed': [('readonly', True)]},
    )
    difference_account_id = fields.Many2one(
        'account.account', string='Difference Account',
        help='Account for payment difference (default: 214100 Accrued Expenses).',
        states={'confirmed': [('readonly', True)]},
    )

    # ── Result ──────────────────────────────────────────────────────────
    payment_id = fields.Many2one(
        'account.payment', string='Payment', readonly=True, copy=False,
    )
    move_id = fields.Many2one(
        'account.move', string='Journal Entry', related='payment_id.move_id',
        store=True, readonly=True,
    )
    # Store all allocated invoices so we can show them as a smart button
    allocated_invoice_ids = fields.Many2many(
        'account.move', 'ar_settlement_invoice_rel',
        'settlement_id', 'invoice_id',
        string='Allocated Invoices', copy=False, readonly=True,
    )
    invoice_count = fields.Integer(
        string='Invoice Count', compute='_compute_invoice_count',
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True, copy=False,
    )

    # ── Posting preview (HTML) ──────────────────────────────────────────
    posting_preview = fields.Html(
        string='Posting Preview', compute='_compute_posting_preview',
        sanitize=False,
    )

    # ═══════════════════════════════════════════════════════════════════
    #  COMPUTED FIELDS
    # ═══════════════════════════════════════════════════════════════════

    @api.depends('allocated_invoice_ids')
    def _compute_invoice_count(self):
        for rec in self:
            rec.invoice_count = len(rec.allocated_invoice_ids)

    @api.depends('partner_id', 'partner_id.vat')
    def _compute_vat_group(self):
        for rec in self:
            rec.vat_group = rec.partner_id.vat or ''

    @api.depends(
        'amount_received', 'bank_fee',
        'line_ids.pay_amount', 'line_ids.selected',
        'credit_line_ids.use_amount',
    )
    def _compute_totals(self):
        for rec in self:
            rec.credit_used = sum(rec.credit_line_ids.mapped('use_amount'))
            selected = rec.line_ids.filtered('selected')
            rec.allocated_amount = sum(selected.mapped('pay_amount'))
            # total_available = gross received + credit notes
            # Bank fee and difference do NOT reduce the allocatable pool
            # (they become separate debit lines in the payment move)
            rec.total_available = rec.amount_received + rec.credit_used
            rec.remaining_amount = rec.total_available - rec.allocated_amount
            rec.difference_amount = rec.total_available - rec.allocated_amount

    @api.depends(
        'amount_received', 'bank_fee', 'allocated_amount',
        'credit_used', 'difference_amount', 'difference_handling',
    )
    def _compute_posting_preview(self):
        for rec in self:
            if not rec.amount_received:
                rec.posting_preview = ''
                continue
            net_bank = rec.amount_received - (rec.bank_fee or 0.0)
            lines = []
            # Dr Bank
            lines.append(('Dr', 'Bank', net_bank))
            # Dr Bank Fee
            if rec.bank_fee:
                lines.append(('Dr', 'Bank Fee Expense', rec.bank_fee))
            # Dr/Cr Accrued Expenses (difference)
            diff = rec.difference_amount or 0.0
            if diff > 0:
                lines.append(('Cr', 'Accrued Expenses (214100)', diff))
            elif diff < 0:
                lines.append(('Dr', 'Accrued Expenses (214100)', abs(diff)))
            # Cr AR
            cr_ar = rec.allocated_amount
            if cr_ar:
                lines.append(('Cr', 'Accounts Receivable', cr_ar))
            # Cr Credit Notes applied
            if rec.credit_used:
                lines.append(('', 'Credit Notes Applied', rec.credit_used))

            html = '<table class="table table-sm table-bordered" style="max-width:500px;">'
            html += '<thead><tr><th></th><th>Account</th><th style="text-align:right;">Amount</th></tr></thead><tbody>'
            for direction, label, amt in lines:
                html += (
                    f'<tr><td><b>{direction}</b></td>'
                    f'<td>{label}</td>'
                    f'<td style="text-align:right;">{amt:,.2f}</td></tr>'
                )
            html += '</tbody></table>'
            rec.posting_preview = html

    # ═══════════════════════════════════════════════════════════════════
    #  ONCHANGE
    # ═══════════════════════════════════════════════════════════════════

    @api.onchange('journal_id')
    def _onchange_journal_id(self):
        if self.journal_id:
            self.currency_id = (
                self.journal_id.currency_id or self.env.company.currency_id
            )

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        self.line_ids = [(5, 0, 0)]
        self.credit_line_ids = [(5, 0, 0)]

    @api.onchange('difference_amount')
    def _onchange_difference_amount(self):
        """Set default difference account from settings when difference exists."""
        if self.difference_amount and not self.difference_account_id:
            param = self.env['ir.config_parameter'].sudo().get_param(
                'account_ar_settlement.payment_difference_account_id'
            )
            if param:
                try:
                    self.difference_account_id = int(param)
                except (ValueError, TypeError):
                    pass

    # ═══════════════════════════════════════════════════════════════════
    #  CRUD OVERRIDES
    # ═══════════════════════════════════════════════════════════════════

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = (
                    self.env['ir.sequence'].next_by_code('ar.settlement')
                    or 'New'
                )
        return super().create(vals_list)

    # ═══════════════════════════════════════════════════════════════════
    #  ACTIONS – INVOICE / CREDIT NOTE LOADING
    # ═══════════════════════════════════════════════════════════════════

    def action_load_invoices(self):
        """Load open invoices matching VAT group and optional trade channel."""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Cannot load invoices on a confirmed settlement.'))

        domain = [
            ('state', '=', 'posted'),
            ('move_type', '=', 'out_invoice'),
            ('payment_state', 'in', ['not_paid', 'partial']),
        ]

        # Date range filter
        if self.filter_date_from:
            domain.append(('invoice_date', '>=', self.filter_date_from))
        if self.filter_date_to:
            domain.append(('invoice_date', '<=', self.filter_date_to))

        # Trade-channel filter (pulls invoices for ALL customers if selected)
        if self.trade_channel:
            invoice_model = self.env['account.move']
            if 'trade_channel' in invoice_model._fields:
                domain.append(('trade_channel', '=', self.trade_channel))
        else:
            # Fall back to VAT-group or Partner filter if no trade channel is selected
            if self.vat_group:
                partners = self.env['res.partner'].search([
                    ('vat', '=', self.vat_group),
                ])
                domain.append(('partner_id', 'in', partners.ids))
            else:
                domain.append(('partner_id', '=', self.partner_id.id))

        invoices = self.env['account.move'].search(domain, order='invoice_date asc')

        lines = [(5, 0, 0)]
        for inv in invoices:
            lines.append((0, 0, {
                'invoice_id': inv.id,
                'pay_amount': inv.amount_residual,
                'selected': True,
            }))
        self.line_ids = lines

        # Also auto-load credit notes
        self._load_credit_notes()

    def _load_credit_notes(self):
        """Load open credit notes matching VAT group."""
        domain = [
            ('state', '=', 'posted'),
            ('move_type', '=', 'out_refund'),
            ('payment_state', 'in', ['not_paid', 'partial']),
            ('amount_residual', '>', 0),
        ]
        if self.vat_group:
            partners = self.env['res.partner'].search([
                ('vat', '=', self.vat_group),
            ])
            domain.append(('partner_id', 'in', partners.ids))
        else:
            domain.append(('partner_id', '=', self.partner_id.id))

        credit_notes = self.env['account.move'].search(
            domain, order='invoice_date asc'
        )
        lines = [(5, 0, 0)]
        for cn in credit_notes:
            residual = abs(cn.amount_residual)
            lines.append((0, 0, {
                'credit_move_id': cn.id,
                'use_amount': residual,
                'selected': True,
            }))
        self.credit_line_ids = lines

    # ═══════════════════════════════════════════════════════════════════
    #  ACTIONS – AUTO ALLOCATE
    # ═══════════════════════════════════════════════════════════════════

    def action_auto_allocate(self):
        """FIFO allocation: fill pay_amount oldest-first up to total_available."""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Cannot auto-allocate on a confirmed settlement.'))

        # Reset all first
        for line in self.line_ids:
            line.pay_amount = 0.0
            line.selected = False

        remaining = self.amount_received + sum(self.credit_line_ids.mapped('use_amount'))
        for line in self.line_ids.sorted(lambda l: l.invoice_date or fields.Date.min):
            if remaining <= 0:
                break
            alloc = min(line.residual, remaining)
            line.pay_amount = alloc
            line.selected = True
            remaining -= alloc

    # ═══════════════════════════════════════════════════════════════════
    #  ACTIONS – CONFIRM
    # ═══════════════════════════════════════════════════════════════════

    def action_confirm(self):
        """Create payment, post, reconcile, handle difference."""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Settlement is already confirmed.'))

        # ── Step 0: Auto-fill pay_amount for selected lines ───────────────
        # Do this FIRST so all subsequent calculations use real amounts.
        inv_selected = self.line_ids.filtered('selected')
        if not inv_selected:
            raise UserError(_('Please tick (select) at least one invoice.'))
        for line in inv_selected:
            if not line.pay_amount:
                line.pay_amount = line.residual

        for cl in self.credit_line_ids.filtered('selected'):
            if not cl.use_amount:
                cl.use_amount = cl.credit_residual

        # Re-filter to valid lines
        inv_selected = inv_selected.filtered(lambda l: l.pay_amount > 0)
        if not inv_selected:
            raise UserError(_('All selected invoices have zero residual.'))

        if self.amount_received <= 0:
            raise UserError(_('Amount received must be greater than zero.'))
        if self.bank_fee and not self.bank_fee_account_id:
            raise UserError(
                _('Please set a Bank Fee Account when bank fee is specified.')
            )

        # Compute diff from actual allocated amounts (not the computed field
        # which may still reflect stale pay_amount=0 values)
        credit_used = sum(self.credit_line_ids.filtered('selected').mapped('use_amount'))
        total_allocated = sum(inv_selected.mapped('pay_amount'))
        diff = (self.amount_received + credit_used) - total_allocated

        if diff != 0 and self.difference_handling in ('credit', 'write_off'):
            if not self.difference_account_id:
                raise UserError(
                    _('Please set a Difference Account to handle the payment difference.')
                )

        # ── 1. Create & post payment ──────────────────────────────────────
        # net = gross received minus bank fee ONLY (never subtract diff here).
        # The AR credit will be raised by _adjust_payment_move to cover all invoices.
        net_amount = self.amount_received - (self.bank_fee or 0.0)
        if net_amount <= 0:
            raise UserError(
                _('Net bank deposit (Received − Bank Fee) must be greater than zero.')
            )
        payment_vals = {
            'partner_id': self.partner_id.id,
            'journal_id': self.journal_id.id,
            'date': self.payment_date,
            'amount': net_amount,
            'currency_id': self.currency_id.id,
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'ref': self.name,
        }
        payment = self.env['account.payment'].create(payment_vals)
        payment.action_post()

        # ── 2. Adjust payment move: add bank-fee / difference lines ────
        # shortfall > 0 = underpayment (we allocated more than received)
        # shortfall < 0 = overpayment  (customer paid more than invoices)
        # shortfall = 0 = exact match (only fee adjustment needed)
        shortfall = total_allocated - (self.amount_received + credit_used)
        if self.bank_fee or (shortfall != 0 and self.difference_handling != 'partial'):
            self._adjust_payment_move(payment, shortfall)

        # ── 3. Reconcile invoices ──────────────────────────────────────────
        for line in inv_selected:
            self._reconcile_invoice(payment, line)

        # ── 4. Apply credit notes ──────────────────────────────────────────
        for cl in self.credit_line_ids.filtered('selected'):
            if cl.use_amount > 0:
                self._reconcile_credit_note(payment, cl)

        # ── 5. Store all allocated invoices for smart button ────────────
        self.allocated_invoice_ids = [(6, 0, inv_selected.mapped('invoice_id').ids)]

        self.payment_id = payment.id
        self.state = 'confirmed'

        return self.action_open_payment()

    # ── Smart button actions ──────────────────────────────────────────────

    def action_open_payment(self):
        """Open the specific payment form record."""
        self.ensure_one()
        if not self.payment_id:
            return {'type': 'ir.actions.act_window_close'}
        return {
            'type': 'ir.actions.act_window',
            'name': _('Payment'),
            'res_model': 'account.payment',
            'res_id': self.payment_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_invoices(self):
        """Open all invoices allocated in this settlement."""
        self.ensure_one()
        invoice_ids = self.allocated_invoice_ids.ids
        if not invoice_ids:
            # Fall back to line_ids for draft records
            invoice_ids = self.line_ids.mapped('invoice_id').ids
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Invoices'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', invoice_ids)],
            'target': 'current',
        }
        if len(invoice_ids) == 1:
            action['view_mode'] = 'form'
            action['res_id'] = invoice_ids[0]
        return action

    # ── helpers ──────────────────────────────────────────────────────────

    def _adjust_payment_move(self, payment, shortfall):
        """Adjust the payment's journal entry to add bank-fee and diff lines.

        shortfall  > 0  →  underpayment: Dr difference_account (company absorbs loss)
        shortfall  < 0  →  overpayment:  Cr difference_account (company keeps excess)
        shortfall  = 0  →  only bank-fee line added

        The AR credit is always set to:
            net (received - fee)  +  fee  +  shortfall  =  total_allocated
        This ensures the entry is self-balancing regardless of sign.

        Resulting entry:
            Dr Bank           [net]            (payment amount)
            Dr Bank Fee       [fee]            (if any)
            Dr Diff Account   [+shortfall]     (underpayment write-off)
         OR Cr Diff Account   [-shortfall]     (overpayment write-off)
            Cr AR             [total_allocated]
        """
        move = payment.move_id
        move.button_draft()

        ar_line = move.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable'
            and l.partner_id == self.partner_id
        )
        if not ar_line:
            move.action_post()
            return

        company_currency = self.env.company.currency_id
        is_foreign = self.currency_id != company_currency

        def _convert(amount):
            if is_foreign:
                return self.currency_id._convert(
                    amount, company_currency,
                    self.env.company, self.payment_date,
                )
            return amount

        new_lines = []

        # Bank fee debit
        if self.bank_fee:
            amt = _convert(self.bank_fee)
            vals = {
                'account_id': self.bank_fee_account_id.id,
                'name': _('Bank Fee'),
                'debit': amt,
                'credit': 0.0,
                'partner_id': self.partner_id.id,
            }
            if is_foreign:
                vals.update({
                    'amount_currency': self.bank_fee,
                    'currency_id': self.currency_id.id,
                })
            else:
                # Same currency: amount_currency must equal debit - credit
                vals['amount_currency'] = amt
            new_lines.append((0, 0, vals))

        # Difference line (only when not 'partial' and shortfall != 0)
        if shortfall and self.difference_handling != 'partial':
            amt = _convert(abs(shortfall))
            if shortfall > 0:
                # Underpayment: company absorbs the loss → Dr difference account
                vals = {
                    'account_id': self.difference_account_id.id,
                    'name': _('Payment Difference – Underpayment'),
                    'debit': amt,
                    'credit': 0.0,
                    'partner_id': self.partner_id.id,
                }
                if is_foreign:
                    vals.update({
                        'amount_currency': shortfall,
                        'currency_id': self.currency_id.id,
                    })
                else:
                    # Same currency: amount_currency = debit - credit = amt
                    vals['amount_currency'] = amt
            else:
                # Overpayment: customer paid extra → Cr difference account
                vals = {
                    'account_id': self.difference_account_id.id,
                    'name': _('Payment Difference – Overpayment'),
                    'debit': 0.0,
                    'credit': amt,
                    'partner_id': self.partner_id.id,
                }
                if is_foreign:
                    vals.update({
                        'amount_currency': shortfall,  # negative
                        'currency_id': self.currency_id.id,
                    })
                else:
                    # Same currency: amount_currency = debit - credit = -amt
                    vals['amount_currency'] = -amt
            new_lines.append((0, 0, vals))

        # Increase AR credit so entry balances:
        #   AR credit = net + fee + shortfall_if_write_off
        #             = (received - fee) + fee + shortfall
        #             = received + shortfall
        #             = total_allocated  ✓
        extra = (self.bank_fee or 0.0)
        if shortfall and self.difference_handling != 'partial':
            extra += shortfall  # shortfall > 0 → raises AR; shortfall < 0 → lowers AR
        extra_company = _convert(extra)

        new_credit = ar_line.credit + extra_company
        ar_vals = {'credit': new_credit}
        if is_foreign:
            ar_vals['amount_currency'] = ar_line.amount_currency - extra
        else:
            # Odoo 17 requires amount_currency == -(credit - debit) even for same currency
            ar_vals['amount_currency'] = -(new_credit - ar_line.debit)
        ar_line.with_context(check_move_validity=False).write(ar_vals)

        if new_lines:
            move.with_context(check_move_validity=False).write(
                {'line_ids': new_lines}
            )
        move.action_post()

    def _reconcile_invoice(self, payment, line):
        """Reconcile payment with invoice.

        - Full pay_amount (>= invoice residual) → standard .reconcile()
        - Partial pay_amount (< invoice residual) → create partial reconcile
          with only the specified pay_amount
        - Diff partner  → create clearing journal entry first
          (Dr AR paying-customer / Cr AR invoice-customer)
          then reconcile invoice ↔ clearing Cr, and payment ↔ clearing Dr.
        """
        invoice = line.invoice_id
        invoice_partner = invoice.partner_id
        pay_amount = line.pay_amount

        if invoice_partner == self.partner_id:
            # ── Same customer: direct reconcile ──────────────────────
            payment_ar = payment.move_id.line_ids.filtered(
                lambda l: l.account_id.account_type == 'asset_receivable'
                and not l.reconciled and l.amount_residual != 0
            )
            invoice_ar = invoice.line_ids.filtered(
                lambda l: l.account_id.account_type == 'asset_receivable'
                and not l.reconciled and l.amount_residual != 0
            )
            if not payment_ar or not invoice_ar:
                return

            invoice_residual = abs(invoice_ar[0].amount_residual)

            if pay_amount >= invoice_residual:
                # Full reconcile: pay_amount covers the entire invoice
                (payment_ar | invoice_ar).reconcile()
            else:
                # Partial reconcile: pay only the specified amount
                company_currency = self.env.company.currency_id
                is_foreign = self.currency_id != company_currency
                amount_company = (
                    self.currency_id._convert(
                        pay_amount, company_currency,
                        self.env.company, self.payment_date)
                    if is_foreign else pay_amount
                )
                self.env['account.partial.reconcile'].create({
                    'debit_move_id': invoice_ar[0].id,
                    'credit_move_id': payment_ar[0].id,
                    'amount': amount_company,
                    'debit_amount_currency': pay_amount if is_foreign else amount_company,
                    'credit_amount_currency': pay_amount if is_foreign else amount_company,
                    'company_id': self.env.company.id,
                })
        else:
            # ── Different customer: create clearing entry ────────────
            self._create_clearing_entry(payment, line)

    def _create_clearing_entry(self, payment, line):
        """Create inter-customer clearing journal entry.

        Entry:
            Dr  AR (paying_partner)   – absorbs payment AR credit
            Cr  AR (invoice_partner)  – closes the invoice AR debit

        Then reconcile:
            1. Invoice AR ↔ Clearing Cr  (marks invoice as paid)
            2. Payment AR ↔ Clearing Dr  (consumes payment credit)
        """
        invoice = line.invoice_id
        invoice_partner = invoice.partner_id
        allocate_amount = line.pay_amount

        # Find the receivable account from the invoice
        receivable_account = invoice.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable'
        ).account_id
        if not receivable_account:
            raise UserError(
                _('Cannot find receivable account for invoice %s') % invoice.name
            )

        # Currency handling
        company_currency = self.env.company.currency_id
        is_foreign = self.currency_id != company_currency

        if is_foreign:
            amount_company = self.currency_id._convert(
                allocate_amount, company_currency,
                self.env.company, self.payment_date,
            )
        else:
            amount_company = allocate_amount

        # Prepare line vals
        if is_foreign:
            debit_vals = {
                'account_id': receivable_account.id,
                'partner_id': self.partner_id.id,
                'debit': amount_company,
                'credit': 0.0,
                'amount_currency': allocate_amount,
                'currency_id': self.currency_id.id,
            }
            credit_vals = {
                'account_id': receivable_account.id,
                'partner_id': invoice_partner.id,
                'debit': 0.0,
                'credit': amount_company,
                'amount_currency': -allocate_amount,
                'currency_id': self.currency_id.id,
            }
        else:
            debit_vals = {
                'account_id': receivable_account.id,
                'partner_id': self.partner_id.id,
                'debit': amount_company,
                'credit': 0.0,
            }
            credit_vals = {
                'account_id': receivable_account.id,
                'partner_id': invoice_partner.id,
                'debit': 0.0,
                'credit': amount_company,
            }

        clearing_move = self.env['account.move'].create({
            'journal_id': self.journal_id.id,
            'date': self.payment_date,
            'ref': _('Clearing: %s → %s [%s]') % (
                self.partner_id.name, invoice_partner.name, invoice.name,
            ),
            'partner_id': self.partner_id.id,
            'line_ids': [
                (0, 0, debit_vals),
                (0, 0, credit_vals),
            ],
        })
        clearing_move.action_post()

        # ── Reconcile invoice AR ↔ clearing credit line ──────────────
        invoice_ar = invoice.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable'
            and not l.reconciled and l.amount_residual != 0
        )
        clearing_cr = clearing_move.line_ids.filtered(
            lambda l: l.partner_id == invoice_partner and l.credit > 0
        )
        if invoice_ar and clearing_cr:
            (invoice_ar | clearing_cr).reconcile()

        # ── Reconcile payment AR ↔ clearing debit line ───────────────
        payment_ar = payment.move_id.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable'
            and not l.reconciled and l.amount_residual != 0
        )
        clearing_dr = clearing_move.line_ids.filtered(
            lambda l: l.partner_id == self.partner_id and l.debit > 0
        )
        if payment_ar and clearing_dr:
            (payment_ar | clearing_dr).reconcile()

        _logger.info(
            'Clearing entry %s created: %s → %s (%.2f)',
            clearing_move.name, self.partner_id.name,
            invoice_partner.name, allocate_amount,
        )

    def _reconcile_credit_note(self, payment, credit_line):
        """Apply a credit note against the settlement's selected invoices.

        Strategy (mirrors batch_payment_wizard):
          - Same partner as paying customer → reconcile CN AR directly
            against payment AR (payment absorbs the credit).
          - Different partner → create a clearing entry to transfer the
            credit to the paying customer's AR, then reconcile both sides.

        The credit reduces what the payment needs to cover.
        """
        cn = credit_line.credit_move_id
        cn_partner = cn.partner_id
        use_amount = credit_line.use_amount or abs(cn.amount_residual)
        if not use_amount:
            return

        # ── Get CN's AR line ──────────────────────────────────────────────
        cn_ar = cn.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable'
            and not l.reconciled
            and l.amount_residual != 0
        )
        if not cn_ar:
            _logger.warning('Credit note %s has no open AR line to reconcile.', cn.name)
            return

        if cn_partner == self.partner_id:
            # ── Same partner: reconcile CN AR ↔ payment AR ──────────────
            payment_ar = payment.move_id.line_ids.filtered(
                lambda l: l.account_id.account_type == 'asset_receivable'
                and not l.reconciled
                and l.amount_residual != 0
            )
            if cn_ar and payment_ar:
                (cn_ar | payment_ar).reconcile()
        else:
            # ── Different partner: clearing entry ─────────────────────────
            # Dr AR (cn_partner)       → absorbs the CN credit residual
            # Cr AR (paying partner)   → gives paying partner the credit amount
            receivable_account = cn_ar.account_id[:1]
            company_currency = self.env.company.currency_id
            is_foreign = self.currency_id != company_currency
            amount_company = (
                self.currency_id._convert(
                    use_amount, company_currency,
                    self.env.company, self.payment_date)
                if is_foreign else use_amount
            )

            if is_foreign:
                debit_vals = {
                    'account_id': receivable_account.id,
                    'partner_id': cn_partner.id,
                    'debit': amount_company, 'credit': 0.0,
                    'amount_currency': use_amount,
                    'currency_id': self.currency_id.id,
                }
                credit_vals = {
                    'account_id': receivable_account.id,
                    'partner_id': self.partner_id.id,
                    'debit': 0.0, 'credit': amount_company,
                    'amount_currency': -use_amount,
                    'currency_id': self.currency_id.id,
                }
            else:
                debit_vals = {
                    'account_id': receivable_account.id,
                    'partner_id': cn_partner.id,
                    'debit': amount_company, 'credit': 0.0,
                }
                credit_vals = {
                    'account_id': receivable_account.id,
                    'partner_id': self.partner_id.id,
                    'debit': 0.0, 'credit': amount_company,
                }

            clearing_move = self.env['account.move'].create({
                'journal_id': self.journal_id.id,
                'date': self.payment_date,
                'ref': _('CN Clearing: %s → %s [%s]') % (
                    cn_partner.name, self.partner_id.name, cn.name),
                'partner_id': self.partner_id.id,
                'line_ids': [(0, 0, debit_vals), (0, 0, credit_vals)],
            })
            clearing_move.action_post()

            # Reconcile CN AR ↔ clearing debit (closes the credit note)
            clearing_dr = clearing_move.line_ids.filtered(
                lambda l: l.partner_id == cn_partner and l.debit > 0)
            if cn_ar and clearing_dr:
                (cn_ar | clearing_dr).reconcile()

            # Reconcile clearing credit ↔ payment AR (gives paying partner credit)
            payment_ar = payment.move_id.line_ids.filtered(
                lambda l: l.account_id.account_type == 'asset_receivable'
                and not l.reconciled
                and l.amount_residual != 0
            )
            clearing_cr = clearing_move.line_ids.filtered(
                lambda l: l.partner_id == self.partner_id and l.credit > 0)
            if payment_ar and clearing_cr:
                (payment_ar | clearing_cr).reconcile()

    # ═══════════════════════════════════════════════════════════════════
    #  ACTIONS – CANCEL / DRAFT
    # ═══════════════════════════════════════════════════════════════════

    def action_cancel(self):
        self.ensure_one()
        if self.state != 'confirmed':
            raise UserError(_('Only confirmed settlements can be cancelled.'))
        self.state = 'cancelled'

    def action_draft(self):
        self.ensure_one()
        if self.state not in ('cancelled',):
            raise UserError(_('Only cancelled settlements can be reset to draft.'))
        self.state = 'draft'
