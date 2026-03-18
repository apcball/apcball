# -*- coding: utf-8 -*-

import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hardcoded selection list kept in sync with marketplace_settlement module.
# Using a lambda that dynamically reads from account.move._fields can fail
# at install time when the inherited field is not yet loaded.
# ---------------------------------------------------------------------------
TRADE_CHANNEL_SELECTION = [
    ('shopee', 'Shopee'),
    ('lazada', 'Lazada'),
    ('nocnoc', 'Noc Noc'),
    ('tiktok', 'Tiktok'),
    ('spx', 'SPX'),
    ('online_line_fb', 'ONLINE/Line + Facebook'),
    ('offline_mogen_outlet', 'OFFLINE/Mogen Outlet'),
    ('after_sale_service', 'After sale service'),
    ('installation_service', 'Installation service'),
    ('own_channel_cdc', 'Own channel ( CDC )'),
    ('other', 'Other'),
]


class BuzBatchPaymentWizard(models.TransientModel):
    _name = 'buz.batch.payment.wizard'
    _description = 'Batch Payment Allocation Wizard'

    # ------------------------------------------------------------------
    # Step 1 — Settlement Information
    # ------------------------------------------------------------------
    payment_date = fields.Date(
        string='Payment Date', required=True, default=fields.Date.today)
    journal_id = fields.Many2one(
        'account.journal', string='Payment Journal', required=True,
        domain=[('type', 'in', ['bank', 'cash'])])
    currency_id = fields.Many2one(
        'res.currency', string='Currency', required=True,
        default=lambda self: self.env.company.currency_id)
    received_amount = fields.Monetary(
        string='Total Received from Customers', required=True, currency_field='currency_id',
        help='Gross amount customers paid in total (before any bank fee deduction). '
             'If the bank deducted a fee, enter the GROSS amount here and fill in Bank Charge below. '
             'The net bank deposit will be: Received − Bank Charge − Difference.')
    reference = fields.Char(string='Reference')

    # Clearing partner (payer)
    paying_partner_id = fields.Many2one(
        'res.partner', string='Clearing Customer', required=True,
        help='The customer through which the clearing payment is processed.')

    # Optional adjustments
    bank_charge = fields.Monetary(
        string='Bank Charge', currency_field='currency_id',
        help='Optional bank fee deducted by bank.')
    bank_fee_account_id = fields.Many2one(
        'account.account', string='Bank Fee Account')

    difference_amount = fields.Monetary(
        string='Difference Amount', currency_field='currency_id',
        help='Manual settlement difference (positive = extra debit, negative = extra credit).')
    difference_account_id = fields.Many2one(
        'account.account', string='Difference Account')

    # ------------------------------------------------------------------
    # Invoice Filters
    # ------------------------------------------------------------------
    vat = fields.Char(string='VAT')
    trade_channel = fields.Selection(
        selection=TRADE_CHANNEL_SELECTION,
        string='Trade Channel')
    date_from = fields.Date(string='Date From')
    date_to = fields.Date(string='Date To')

    # ------------------------------------------------------------------
    # Lines
    # ------------------------------------------------------------------
    allocation_line_ids = fields.One2many(
        'buz.batch.payment.line', 'wizard_id', string='Allocations')

    # ------------------------------------------------------------------
    # Computed Summary
    # ------------------------------------------------------------------
    total_invoice_amount = fields.Monetary(
        string='Total Invoice Amount', compute='_compute_totals',
        currency_field='currency_id')
    total_allocated = fields.Monetary(
        string='Total Allocated', compute='_compute_totals',
        currency_field='currency_id')
    remaining_balance = fields.Monetary(
        string='Remaining Balance', compute='_compute_totals',
        currency_field='currency_id')

    state = fields.Selection([
        ('setup', 'Setup Filters'),
        ('allocate', 'Allocate Invoices'),
        ('review', 'Review & Confirm'),
    ], string='State', default='setup')

    # ------------------------------------------------------------------
    # Computed
    # ------------------------------------------------------------------
    @api.depends(
        'allocation_line_ids.allocate_amount',
        'allocation_line_ids.selected',
        'received_amount', 'bank_charge', 'difference_amount')
    def _compute_totals(self):
        for wizard in self:
            selected = wizard.allocation_line_ids.filtered('selected')
            wizard.total_allocated = sum(selected.mapped('allocate_amount'))
            wizard.total_invoice_amount = sum(
                wizard.allocation_line_ids.mapped('residual'))
            # Remaining = received_amount (gross) - allocated.
            # Bank charge and difference are costs absorbed separately;
            # they do NOT increase how much needs to be allocated.
            wizard.remaining_balance = (
                wizard.received_amount - wizard.total_allocated)

    # ------------------------------------------------------------------
    # Onchange
    # ------------------------------------------------------------------
    @api.onchange('journal_id')
    def _onchange_journal_id(self):
        if self.journal_id:
            self.currency_id = (
                self.journal_id.currency_id or self.env.company.currency_id)

    @api.onchange('vat', 'trade_channel', 'date_from', 'date_to')
    def _onchange_filters(self):
        """Clear allocation lines when any filter changes."""
        if self.state != 'setup':
            self.allocation_line_ids = [(5, 0, 0)]
            self.state = 'setup'

    # ------------------------------------------------------------------
    # Navigation actions
    # ------------------------------------------------------------------
    def _return_self(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_load_invoices(self):
        """Load invoices based on current filters (Step 1 → Step 2)."""
        domain = [
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ['not_paid', 'partial']),
        ]

        if self.vat:
            domain.append(('commercial_partner_id.vat', '=', self.vat))
        if self.trade_channel:
            domain.append(('trade_channel', '=', self.trade_channel))
        if self.date_from:
            domain.append(('invoice_date', '>=', self.date_from))
        if self.date_to:
            domain.append(('invoice_date', '<=', self.date_to))

        invoices = self.env['account.move'].search(domain, order='invoice_date asc')

        lines = [(5, 0, 0)]
        for inv in invoices:
            lines.append((0, 0, {
                'invoice_id': inv.id,
                'allocate_amount': 0.0,
                'selected': False,
            }))

        self.allocation_line_ids = lines
        self.state = 'allocate'
        return self._return_self()

    def action_auto_allocate(self):
        """FIFO allocation: distribute received_amount across invoices sorted by date.

        Bank charge and difference are absorbed as separate expense entries and
        do NOT increase the amount available for invoice allocation.
        """
        available = self.received_amount

        # Reset
        for line in self.allocation_line_ids:
            line.allocate_amount = 0.0
            line.selected = False

        remaining = available
        sorted_lines = self.allocation_line_ids.sorted(
            key=lambda l: l.invoice_date or fields.Date.today())

        for line in sorted_lines:
            if remaining <= 0:
                break
            allocate = min(line.residual, remaining)
            line.allocate_amount = allocate
            line.selected = True
            remaining -= allocate

        return self._return_self()

    def action_next(self):
        if self.state == 'setup':
            return self.action_load_invoices()

        elif self.state == 'allocate':
            if not any(line.selected for line in self.allocation_line_ids):
                raise ValidationError(
                    _("Please select and allocate at least one invoice."))

            # remaining_balance may be up to (bank_charge + difference_amount):
            #   0             → perfectly allocated
            #   0 < rem ≤ adj → the bank charge/difference explains the gap (OK)
            #   rem > adj     → genuinely under-allocated (error)
            #   rem < 0       → over-allocated (error)
            adj = self.bank_charge + self.difference_amount
            if self.remaining_balance < 0:
                raise ValidationError(_(
                    "Over-allocated by %(over)s. "
                    "Please reduce the allocation amounts.",
                    over=-self.remaining_balance,
                ))
            if self.remaining_balance > adj:
                raise ValidationError(_(
                    "Still %(remaining)s unallocated after accounting for "
                    "Bank Charge + Difference (%(adj)s). "
                    "Please allocate more invoices or increase the adjustment amounts.",
                    remaining=self.remaining_balance,
                    adj=adj,
                ))
            if self.bank_charge and not self.bank_fee_account_id:
                raise ValidationError(
                    _("Please provide a Bank Fee Account when Bank Charge is specified."))
            if self.difference_amount and not self.difference_account_id:
                raise ValidationError(
                    _("Please provide a Difference Account when Difference Amount is specified."))
            if not self.paying_partner_id:
                raise ValidationError(_("Please set a Clearing Customer."))

            self.state = 'review'

        return self._return_self()

    def action_previous(self):
        if self.state == 'allocate':
            self.state = 'setup'
        elif self.state == 'review':
            self.state = 'allocate'
        return self._return_self()

    # ------------------------------------------------------------------
    # Confirm & Post
    # ------------------------------------------------------------------
    def action_confirm_and_post(self):
        """
        Creates the batch payment and for each allocated invoice either:
          - Reconciles directly (same partner as paying_partner_id), or
          - Creates a clearing journal entry and reconciles through it.

        Journal entry created by the payment (before adjustments):
            Dr  Bank / Cash                    [received_amount]
            Cr  AR (Clearing Customer)         [received_amount]

        After _handle_expense_difference_lines (if applicable):
            Dr  Bank / Cash                    [received_amount]
            Dr  Bank Fee Expense               [bank_charge]
            Dr  Difference Account             [difference_amount]  (if positive)
            Cr  Difference Account             [|difference_amount|] (if negative)
            Cr  AR (Clearing Customer)         [received + charge + difference]
        """
        self.ensure_one()
        selected_lines = self.allocation_line_ids.filtered(
            lambda l: l.selected and l.allocate_amount > 0)
        if not selected_lines:
            raise ValidationError(
                _("Please select at least one invoice to allocate payment."))

        # ------------------------------------------------------------------
        # 1. Create and post the payment
        #    The Odoo payment move will post:
        #      Dr Bank      [received_amount]
        #      Cr AR        [received_amount]   (partner = paying_partner_id)
        # ------------------------------------------------------------------
        # Net bank deposit = gross received − bank charge − difference.
        # The bank_charge/difference are posted as separate expense debit lines
        # by _handle_expense_difference_lines, which also increases the AR
        # credit to cover the full gross amount (= total allocated invoices).
        net_amount = self.received_amount - self.bank_charge - self.difference_amount
        if net_amount <= 0:
            raise ValidationError(
                _("Net bank deposit (Received − Bank Charge − Difference) must be "
                  "greater than zero. Current net: %(net)s", net=net_amount))

        payment_vals = {
            'partner_id': self.paying_partner_id.id,
            'journal_id': self.journal_id.id,
            'date': self.payment_date,
            'amount': net_amount,
            'currency_id': self.currency_id.id,
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'ref': self.reference or _('Batch Settlement'),
            'is_clearing_payment': True,
        }
        payment = self.env['account.payment'].create(payment_vals)
        payment.action_post()

        # ------------------------------------------------------------------
        # 2. Adjust the AR credit line to cover bank charge + difference.
        #    This keeps the entry balanced and gives enough AR credit to later
        #    reconcile all selected invoices (possibly via clearing entries).
        # ------------------------------------------------------------------
        if self.bank_charge or self.difference_amount:
            self._handle_expense_difference_lines(payment)

        # ------------------------------------------------------------------
        # 3. Process each allocated invoice
        # ------------------------------------------------------------------
        for line in selected_lines:
            try:
                if line.partner_id == self.paying_partner_id:
                    self._reconcile_same_customer(payment, line)
                else:
                    self._create_clearing_entry(payment, line)
            except Exception as exc:
                raise UserError(_(
                    "Error processing invoice %(inv)s: %(err)s",
                    inv=line.invoice_id.name,
                    err=str(exc),
                )) from exc

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _(
                    'Batch Payment created and %(count)s invoice(s) have been '
                    'allocated and reconciled.',
                    count=len(selected_lines)),
                'type': 'success',
                'sticky': False,
            },
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _handle_expense_difference_lines(self, payment):
        """
        Adjusts the posted payment move to add bank charge / difference lines.

        Strategy:
          1. Reset the move to draft.
          2. Add extra debit lines (bank fee, difference).
          3. Increase the AR credit by the same total so the entry stays balanced.
          4. Re-post.

        Final entry:
            Dr  Bank/Cash          [received_amount]          (unchanged — written by Odoo)
            Dr  Bank Fee Expense   [bank_charge]              (added here)
            Dr  Difference Acct    [difference_amount]        (added here, if > 0)
            Cr  Difference Acct    [|difference_amount|]      (added here, if < 0)
            Cr  AR Clearing Cust   [received + charge + diff] (AR line increased here)
        """
        move = payment.move_id
        extra_total = self.bank_charge + self.difference_amount  # signed sum

        move.button_draft()

        # Find the AR line for the clearing partner
        ar_line = move.line_ids.filtered(
            lambda l: (
                l.account_id.account_type == 'asset_receivable'
                and l.partner_id == self.paying_partner_id
            )
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
                    self.env.company, self.payment_date)
            return amount

        new_line_cmds = []

        # Bank charge line (debit)
        if self.bank_charge:
            amt_company = _convert(self.bank_charge)
            vals = {
                'account_id': self.bank_fee_account_id.id,
                'name': _('Bank Charge'),
                'debit': amt_company,
                'credit': 0.0,
                'partner_id': self.paying_partner_id.id,
            }
            if is_foreign:
                vals.update({
                    'amount_currency': self.bank_charge,
                    'currency_id': self.currency_id.id,
                })
            new_line_cmds.append((0, 0, vals))

        # Difference line (debit if positive, credit if negative)
        if self.difference_amount:
            amt_company = _convert(abs(self.difference_amount))
            if self.difference_amount > 0:
                vals = {
                    'account_id': self.difference_account_id.id,
                    'name': _('Settlement Difference'),
                    'debit': amt_company,
                    'credit': 0.0,
                    'partner_id': self.paying_partner_id.id,
                }
            else:
                vals = {
                    'account_id': self.difference_account_id.id,
                    'name': _('Settlement Difference'),
                    'debit': 0.0,
                    'credit': amt_company,
                    'partner_id': self.paying_partner_id.id,
                }
            if is_foreign:
                vals.update({
                    'amount_currency': self.difference_amount,
                    'currency_id': self.currency_id.id,
                })
            new_line_cmds.append((0, 0, vals))

        # Increase AR credit by extra_total (so entry stays balanced)
        extra_company = _convert(extra_total)
        ar_line_vals = {
            'credit': ar_line.credit + extra_company,
        }
        if is_foreign:
            ar_line_vals['amount_currency'] = (
                ar_line.amount_currency - extra_total)

        ar_line.with_context(check_move_validity=False).write(ar_line_vals)

        if new_line_cmds:
            move.with_context(check_move_validity=False).write(
                {'line_ids': new_line_cmds})

        move.action_post()

    def _reconcile_same_customer(self, payment, line):
        """
        Direct reconciliation when the invoice partner equals the paying partner.
        No clearing entry needed — just reconcile the payment AR line against
        the invoice AR line.
        """
        payment_ar = payment.move_id.line_ids.filtered(
            lambda l: (
                l.account_id.account_type == 'asset_receivable'
                and not l.reconciled
                and l.amount_residual != 0
            )
        )
        invoice_ar = line.invoice_id.line_ids.filtered(
            lambda l: (
                l.account_id.account_type == 'asset_receivable'
                and not l.reconciled
                and l.amount_residual != 0
            )
        )

        if not payment_ar or not invoice_ar:
            _logger.warning(
                'Batch payment: could not find AR lines to reconcile for '
                'invoice %s (same-customer path).',
                line.invoice_id.name)
            return

        (payment_ar | invoice_ar).reconcile()

        # Mark reconciliation records
        partial_recs = (
            payment_ar.matched_debit_ids
            | payment_ar.matched_credit_ids
            | invoice_ar.matched_debit_ids
            | invoice_ar.matched_credit_ids
        )
        partial_recs.filtered(
            lambda r: not r.is_clearing_reconcile
        ).write({
            'is_clearing_reconcile': True,
            'clearing_payment_id': payment.id,
        })

        # Audit link
        self.env['buz.clearing.link'].create({
            'payment_id': payment.id,
            'invoice_id': line.invoice_id.id,
            'amount': line.allocate_amount,
            'date': self.payment_date,
            'settlement_batch': self.reference or _('Batch Settlement'),
            'invoice_date': line.invoice_date,
        })

    def _create_clearing_entry(self, payment, line):
        """
        Creates an inter-customer clearing journal entry when the invoice
        partner differs from the paying partner, then reconciles:
          - Invoice AR  ↔  Clearing Credit (invoice_partner)  → closes the invoice
          - Payment AR  ↔  Clearing Debit  (paying_partner)   → draws from payment funds

        Clearing entry (correct direction):
            Dr  AR (Clearing/Paying Customer)  [amount]  ← draws from payment AR credit
            Cr  AR (Invoice Customer)          [amount]  ← closes the invoice AR debit
        """
        invoice = line.invoice_id
        invoice_partner = line.partner_id
        allocate_amount = line.allocate_amount
        currency = line.currency_id or self.currency_id

        if not allocate_amount or allocate_amount <= 0:
            raise UserError(
                _('Allocation amount must be greater than 0 for invoice %s.')
                % invoice.name)

        # Find the receivable account used by the invoice
        receivable_account = invoice.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable'
        ).account_id
        if not receivable_account:
            raise UserError(
                _('Cannot find receivable account for invoice %s.') % invoice.name)

        # Currency handling
        company_currency = self.env.company.currency_id
        is_foreign = currency != company_currency
        if is_foreign:
            amount_company = currency._convert(
                allocate_amount, company_currency,
                self.env.company, self.payment_date or fields.Date.today())
        else:
            amount_company = allocate_amount

        if not amount_company or amount_company <= 0:
            raise UserError(
                _('Invalid amount for invoice %s (amount: %s).')
                % (invoice.name, amount_company))

        # Build journal entry lines.
        # Debit  = paying_partner  → absorbs the payment AR credit
        # Credit = invoice_partner → cancels the invoice AR debit
        if is_foreign:
            debit_vals = {
                'account_id': receivable_account.id,
                'partner_id': self.paying_partner_id.id,
                'debit': amount_company,
                'credit': 0.0,
                'amount_currency': allocate_amount,
                'currency_id': currency.id,
            }
            credit_vals = {
                'account_id': receivable_account.id,
                'partner_id': invoice_partner.id,
                'debit': 0.0,
                'credit': amount_company,
                'amount_currency': -allocate_amount,
                'currency_id': currency.id,
            }
        else:
            debit_vals = {
                'account_id': receivable_account.id,
                'partner_id': self.paying_partner_id.id,
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
            'ref': _('Batch Clearing: %s → %s [%s]') % (
                self.paying_partner_id.name,
                invoice_partner.name,
                invoice.name,
            ),
            'partner_id': self.paying_partner_id.id,
            'is_clearing_entry': True,
            'clearing_payment_id': payment.id,
            'line_ids': [(0, 0, debit_vals), (0, 0, credit_vals)],
        })
        clearing_move.action_post()

        # ---- Reconcile invoice AR ↔ clearing credit line ----
        invoice_ar = invoice.line_ids.filtered(
            lambda l: (
                l.account_id.account_type == 'asset_receivable'
                and not l.reconciled
                and l.amount_residual != 0
            )
        )
        # clearing_credit = credit line on invoice_partner's AR → matches invoice_ar (Dr)
        clearing_credit = clearing_move.line_ids.filtered(
            lambda l: l.partner_id == invoice_partner and l.credit > 0)

        if invoice_ar and clearing_credit:
            (invoice_ar | clearing_credit).reconcile()
            partial_recs = (
                invoice_ar.matched_debit_ids | invoice_ar.matched_credit_ids
                | clearing_credit.matched_debit_ids
                | clearing_credit.matched_credit_ids
            )
            partial_recs.filtered(
                lambda r: not r.is_clearing_reconcile
            ).write({
                'is_clearing_reconcile': True,
                'clearing_payment_id': payment.id,
            })
        else:
            _logger.warning(
                'Batch clearing: could not reconcile invoice AR for %s.',
                invoice.name)

        # ---- Reconcile payment AR ↔ clearing debit line ----
        payment_ar = payment.move_id.line_ids.filtered(
            lambda l: (
                l.account_id.account_type == 'asset_receivable'
                and not l.reconciled
                and l.amount_residual != 0
            )
        )
        # clearing_debit = debit line on paying_partner's AR → matches payment_ar (Cr)
        clearing_debit = clearing_move.line_ids.filtered(
            lambda l: l.partner_id == self.paying_partner_id and l.debit > 0)

        if payment_ar and clearing_debit:
            (payment_ar | clearing_debit).reconcile()
            partial_recs = (
                payment_ar.matched_debit_ids | payment_ar.matched_credit_ids
                | clearing_debit.matched_debit_ids
                | clearing_debit.matched_credit_ids
            )
            partial_recs.filtered(
                lambda r: not r.is_clearing_reconcile
            ).write({
                'is_clearing_reconcile': True,
                'clearing_payment_id': payment.id,
            })
        else:
            _logger.warning(
                'Batch clearing: could not reconcile payment AR for %s.',
                invoice.name)

        # ---- Audit link ----
        self.env['buz.clearing.link'].create({
            'payment_id': payment.id,
            'clearing_move_id': clearing_move.id,
            'invoice_id': invoice.id,
            'amount': allocate_amount,
            'date': self.payment_date,
            'settlement_batch': self.reference or _('Batch Settlement'),
            'invoice_date': line.invoice_date,
            'trade_channel': line.trade_channel or False,
        })
