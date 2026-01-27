# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime


class BuzClearingPaymentWizard(models.TransientModel):
    _name = 'buz.clearing.payment.wizard'
    _description = 'Inter-Customer Clearing Payment Wizard'
    
    # Step 1: Payment Header
    paying_partner_id = fields.Many2one(
        'res.partner', string='Paying Customer', required=True,
        domain=[('is_company', '=', True), ('vat', '!=', False)]
    )
    paying_partner_tax_id = fields.Char(
        string='Tax ID', compute='_compute_paying_partner_tax_id', readonly=True,
        help='Tax ID of the selected paying customer'
    )
    journal_id = fields.Many2one(
        'account.journal', string='Payment Journal', required=True,
        domain=[('type', 'in', ['bank', 'cash'])]
    )
    payment_date = fields.Date(
        string='Payment Date', required=True, default=fields.Date.today
    )
    currency_id = fields.Many2one(
        'res.currency', string='Currency', required=True,
        default=lambda self: self.env.company.currency_id
    )
    amount = fields.Monetary(
        string='Payment Amount', required=True, currency_field='currency_id'
    )
    reference = fields.Char(
        string='Reference'
    )
    
    # Step 2: Allocation
    allocation_line_ids = fields.One2many(
        'buz.clearing.payment.line', 'wizard_id', string='Allocations'
    )
    
    # Credit Notes
    credit_line_ids = fields.One2many(
        'buz.clearing.payment.credit.line', 'wizard_id', string='Credit Notes'
    )
    
    # Computed fields
    total_credit_note = fields.Monetary(
        string='Total Credit Note', compute='_compute_totals',
        currency_field='currency_id'
    )
    total_available = fields.Monetary(
        string='Total Available', compute='_compute_totals',
        currency_field='currency_id',
        help='Payment Amount + Credit Notes'
    )
    total_allocated = fields.Monetary(
        string='Total Allocated', compute='_compute_totals', 
        currency_field='currency_id'
    )
    remaining_amount = fields.Monetary(
        string='Remaining Amount', compute='_compute_totals', 
        currency_field='currency_id'
    )
    state = fields.Selection([
        ('header', 'Payment Header'),
        ('credit_notes', 'Select Credit Notes'),
        ('allocate', 'Allocate Invoices'),
        ('review', 'Review & Confirm'),
    ], string='State', default='header')
    
    @api.depends('paying_partner_id')
    def _compute_paying_partner_tax_id(self):
        """Compute tax ID of paying customer"""
        for wizard in self:
            wizard.paying_partner_tax_id = wizard.paying_partner_id.vat or ''
    
    @api.depends('amount', 'credit_line_ids.use_amount', 'allocation_line_ids.allocate_amount')
    def _compute_totals(self):
        for wizard in self:
            wizard.total_credit_note = sum(
                line.use_amount for line in wizard.credit_line_ids if line.selected
            )
            wizard.total_available = wizard.amount + wizard.total_credit_note
            wizard.total_allocated = sum(wizard.allocation_line_ids.mapped('allocate_amount'))
            wizard.remaining_amount = wizard.total_available - wizard.total_allocated
    
    @api.onchange('journal_id')
    def onchange_journal_id(self):
        """Set currency based on journal"""
        if self.journal_id:
            self.currency_id = self.journal_id.currency_id or self.env.company.currency_id
    
    @api.onchange('paying_partner_id')
    def onchange_paying_partner_id(self):
        """Clear allocation and credit note lines when paying partner changes"""
        self.allocation_line_ids = [(5, 0, 0)]
        self.credit_line_ids = [(5, 0, 0)]
    
    def action_next(self):
        """Move to next step"""
        if self.state == 'header':
            # Validate header
            if not self.paying_partner_id:
                raise ValidationError(_('Please select a paying customer.'))
            if not self.journal_id:
                raise ValidationError(_('Please select a payment journal.'))
            if not self.amount or self.amount <= 0:
                raise ValidationError(_('Payment amount must be greater than 0.'))
            
            # Load available credit notes
            self._load_available_credit_notes()
            
            self.state = 'credit_notes'
            return {
                'type': 'ir.actions.act_window',
                'res_model': self._name,
                'res_id': self.id,
                'view_mode': 'form',
                'view_id': self.env.ref('buz_inter_customer_clearing_payment.view_clearing_payment_wizard_credit_notes').id,
                'target': 'new',
                'context': self.env.context,
            }
        
        elif self.state == 'credit_notes':
            # Load available invoices
            self._load_available_invoices()
            
            self.state = 'allocate'
            return {
                'type': 'ir.actions.act_window',
                'res_model': self._name,
                'res_id': self.id,
                'view_mode': 'form',
                'view_id': self.env.ref('buz_inter_customer_clearing_payment.view_clearing_payment_wizard_form').id,
                'target': 'new',
                'context': self.env.context,
            }
        
        elif self.state == 'allocate':
            # Validate allocations
            if not any(line.selected for line in self.allocation_line_ids):
                raise ValidationError(_('Please select at least one invoice to allocate.'))
            
            self.state = 'review'
            return {
                'type': 'ir.actions.act_window',
                'res_model': self._name,
                'res_id': self.id,
                'view_mode': 'form',
                'view_id': self.env.ref('buz_inter_customer_clearing_payment.view_clearing_payment_wizard_review').id,
                'target': 'new',
                'context': self.env.context,
            }
        
        return {'type': 'ir.actions.act_window_close'}
    
    def action_previous(self):
        """Move to previous step"""
        if self.state == 'credit_notes':
            self.state = 'header'
        elif self.state == 'allocate':
            self.state = 'credit_notes'
        elif self.state == 'review':
            self.state = 'allocate'
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': self.env.ref('buz_inter_customer_clearing_payment.view_clearing_payment_wizard_form').id,
            'target': 'new',
            'context': self.env.context,
        }
    
    def action_auto_fill_fifo(self):
        """Auto-fill allocations using FIFO logic filtered by Tax ID"""
        if not self.paying_partner_id or not self.paying_partner_id.vat:
            raise ValidationError(
                _('Paying customer must have a Tax ID to use auto-fill feature.')
            )
        
        # Get all customers with the same Tax ID
        partner_with_same_tax = self.env['res.partner'].search([
            ('vat', '=', self.paying_partner_id.vat),
        ])
        
        # Get all unpaid invoices from customers with same Tax ID, sorted by date
        invoices = self.env['account.move'].search([
            ('partner_id', 'in', partner_with_same_tax.ids),
            ('state', '=', 'posted'),
            ('move_type', '=', 'out_invoice'),
            ('payment_state', 'in', ['not_paid', 'partial']),
        ], order='invoice_date asc')
        
        # Use total available (payment + credit notes)
        remaining = self.total_available
        allocation_lines = []
        
        for invoice in invoices:
            if remaining <= 0:
                break
            
            residual = invoice.amount_residual
            allocate = min(residual, remaining)
            
            allocation_lines.append((0, 0, {
                'invoice_id': invoice.id,
                'selected': True,
                'allocate_amount': allocate,
            }))
            
            remaining -= allocate
        
        self.allocation_line_ids = allocation_lines
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': self.env.ref('buz_inter_customer_clearing_payment.view_clearing_payment_wizard_form').id,
            'target': 'new',
            'context': self.env.context,
        }
    
    def action_clear_allocation(self):
        """Clear all allocations"""
        self.allocation_line_ids = [(5, 0, 0)]
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': self.env.ref('buz_inter_customer_clearing_payment.view_clearing_payment_wizard_form').id,
            'target': 'new',
            'context': self.env.context,
        }
    
    def action_confirm_and_post(self):
        """Create payment and clearing entries"""
        # Validate total allocation
        if self.total_allocated > self.total_available:
            raise ValidationError(_('Total allocated amount cannot exceed total available amount (Payment + Credit Notes).'))
        
        # Validate that we have allocations
        selected_lines = self.allocation_line_ids.filtered(lambda l: l.selected and l.allocate_amount > 0)
        if not selected_lines:
            raise ValidationError(_('Please select at least one invoice to allocate payment.'))
        
        # Create payment
        payment_vals = {
            'partner_id': self.paying_partner_id.id,
            'journal_id': self.journal_id.id,
            'date': self.payment_date,
            'amount': self.amount,
            'currency_id': self.currency_id.id,
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'ref': self.reference,
            'is_clearing_payment': True,
            'clearing_advance_amount': self.remaining_amount,
        }
        
        payment = self.env['account.payment'].create(payment_vals)
        payment.action_post()
        
        import logging
        _logger = logging.getLogger(__name__)
        _logger.info('='*80)
        _logger.info('Payment created: %s', payment.name)
        _logger.info('Selected lines count: %s', len(selected_lines))
        
        # Process Credit Notes first (if any)
        selected_credit_lines = self.credit_line_ids.filtered(lambda l: l.selected and l.use_amount > 0)
        _logger.info('Selected credit note lines count: %s', len(selected_credit_lines))
        
        for credit_line in selected_credit_lines:
            _logger.info('---')
            _logger.info('Processing Credit Note: %s', credit_line.credit_note_id.name)
            _logger.info('Credit Note Partner: %s (ID: %s)', credit_line.credit_note_partner_id.name, credit_line.credit_note_partner_id.id)
            _logger.info('Use amount: %s', credit_line.use_amount)
            
            # Check if credit note partner is same as paying partner
            if credit_line.credit_note_partner_id == self.paying_partner_id:
                _logger.info('-> Same partner - Direct reconciliation for credit note')
                # Direct reconciliation - just reconcile credit note with payment
                self._reconcile_credit_note_same_customer(payment, credit_line)
            else:
                _logger.info('-> Different partner - Create clearing entry for credit note')
                # Create clearing entry for different customer
                self._create_credit_note_clearing_entry(payment, credit_line)
        
        # Process allocations
        for line in selected_lines:
            _logger.info('---')
            _logger.info('Processing line - Invoice: %s', line.invoice_id.name)
            _logger.info('Invoice Partner: %s (ID: %s)', line.invoice_partner_id.name, line.invoice_partner_id.id)
            _logger.info('Paying Partner: %s (ID: %s)', self.paying_partner_id.name, self.paying_partner_id.id)
            _logger.info('Same partner? %s', line.invoice_partner_id == self.paying_partner_id)
            _logger.info('Allocate amount: %s', line.allocate_amount)
            
            # Skip if paying customer is the same as invoice customer
            if line.invoice_partner_id == self.paying_partner_id:
                _logger.info('-> Calling _reconcile_same_customer')
                # Direct reconciliation for same customer
                self._reconcile_same_customer(payment, line)
            else:
                _logger.info('-> Calling _create_clearing_entry')
                # Create clearing entry for different customer
                self._create_clearing_entry(payment, line)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Payment and allocations have been processed successfully.'),
                'type': 'success',
                'sticky': False,
            }
        }
    
    def _load_available_invoices(self):
        """Load all available invoices filtered by same Tax ID as paying customer"""
        if not self.paying_partner_id or not self.paying_partner_id.vat:
            raise ValidationError(
                _('Paying customer must have a Tax ID (VAT) to proceed with clearing payment.')
            )
        
        # Get all customers with the same Tax ID
        partner_with_same_tax = self.env['res.partner'].search([
            ('vat', '=', self.paying_partner_id.vat),
        ])
        
        # Load invoices from customers with same Tax ID
        invoices = self.env['account.move'].search([
            ('partner_id', 'in', partner_with_same_tax.ids),
            ('state', '=', 'posted'),
            ('move_type', '=', 'out_invoice'),
            ('payment_state', 'in', ['not_paid', 'partial']),
        ])
        
        allocation_lines = []
        for invoice in invoices:
            allocation_lines.append((0, 0, {
                'invoice_id': invoice.id,
                'selected': False,
                'allocate_amount': 0.0,
            }))
        
        self.allocation_line_ids = allocation_lines
    
    def _load_available_credit_notes(self):
        """Load all available credit notes filtered by same Tax ID as paying customer"""
        if not self.paying_partner_id or not self.paying_partner_id.vat:
            raise ValidationError(
                _('Paying customer must have a Tax ID (VAT) to proceed with clearing payment.')
            )
        
        # Get all customers with the same Tax ID
        partner_with_same_tax = self.env['res.partner'].search([
            ('vat', '=', self.paying_partner_id.vat),
        ])
        
        # Load credit notes from customers with same Tax ID
        credit_notes = self.env['account.move'].search([
            ('partner_id', 'in', partner_with_same_tax.ids),
            ('state', '=', 'posted'),
            ('move_type', '=', 'out_refund'),
            ('payment_state', 'in', ['not_paid', 'partial']),
            ('amount_residual', '>', 0),
            ('currency_id', '=', self.currency_id.id),
        ], order='invoice_date asc')
        
        credit_lines = []
        for credit_note in credit_notes:
            residual = abs(credit_note.amount_residual)  # Use absolute value for credit notes
            credit_lines.append((0, 0, {
                'credit_note_id': credit_note.id,
                'selected': True,  # Auto-select all available credit notes
                'use_amount': residual,  # Auto-fill with full residual amount
            }))
        
        self.credit_line_ids = credit_lines
    
    def _reconcile_same_customer(self, payment, line):
        """Reconcile payment with invoice for same customer"""
        # Find the UNRECONCILED receivable lines only
        payment_line = payment.move_id.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable'
            and not l.reconciled
            and l.amount_residual != 0
        )
        invoice_line = line.invoice_id.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable'
            and not l.reconciled
            and l.amount_residual != 0
        )
        
        if payment_line and invoice_line:
            # Auto reconcile to mark invoice as paid
            lines_to_reconcile = payment_line | invoice_line
            lines_to_reconcile.reconcile()
            
            # Mark reconciliation as clearing reconcile
            partial_reconciles = payment_line.matched_debit_ids | payment_line.matched_credit_ids
            partial_reconciles |= invoice_line.matched_debit_ids | invoice_line.matched_credit_ids
            partial_reconciles.filtered(lambda r: not r.is_clearing_reconcile).write({
                'is_clearing_reconcile': True,
                'clearing_payment_id': payment.id,
            })
            
            # Create clearing link
            self.env['buz.clearing.link'].create({
                'payment_id': payment.id,
                'invoice_id': line.invoice_id.id,
                'amount': line.allocate_amount,
                'date': self.payment_date,
            })
    
    def _create_clearing_entry(self, payment, line):
        """Create clearing journal entry for different customer"""
        # Read and store values before they potentially get lost
        invoice = line.invoice_id
        invoice_partner = line.invoice_partner_id
        allocate_amount = line.allocate_amount
        currency = line.currency_id
        
        import logging
        _logger = logging.getLogger(__name__)
        _logger.info('='*80)
        _logger.info('_create_clearing_entry called')
        _logger.info('Invoice: %s', invoice.name)
        _logger.info('Invoice Partner: %s (ID: %s)', invoice_partner.name, invoice_partner.id)
        _logger.info('Allocate Amount: %s (type: %s)', allocate_amount, type(allocate_amount))
        _logger.info('Currency: %s (ID: %s)', currency.name if currency else 'None', currency.id if currency else 'None')
        _logger.info('Company Currency: %s', self.env.company.currency_id.name)
        
        # Validate allocation amount
        if not allocate_amount or allocate_amount <= 0:
            raise UserError(_('Allocation amount must be greater than 0 for invoice %s') % invoice.name)
        
        # Get accounts
        receivable_account = invoice.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable'
        ).account_id
        
        if not receivable_account:
            raise UserError(_('Cannot find receivable account for invoice %s') % invoice.name)
        
        # Determine if we're using foreign currency
        company_currency = self.env.company.currency_id
        is_foreign_currency = currency != company_currency
        
        # Calculate amounts in company currency
        if is_foreign_currency:
            # Convert foreign currency to company currency
            amount_company_currency = currency._convert(
                allocate_amount,
                company_currency,
                self.env.company,
                self.payment_date or fields.Date.today()
            )
        else:
            # Already in company currency
            amount_company_currency = allocate_amount
        
        # Ensure we have valid amounts
        if not amount_company_currency or amount_company_currency <= 0:
            raise UserError(_('Invalid amount calculation for invoice %s. Amount: %s') % (invoice.name, amount_company_currency))
        
        _logger.info('Amount Company Currency: %s', amount_company_currency)
        _logger.info('Is Foreign Currency: %s', is_foreign_currency)
        
        # Prepare line values based on currency
        if is_foreign_currency:
            debit_line_vals = {
                'account_id': receivable_account.id,
                'partner_id': self.paying_partner_id.id,  # Paying customer gets the debt
                'debit': amount_company_currency,
                'credit': 0.0,
                'amount_currency': allocate_amount,
                'currency_id': currency.id,
            }
            credit_line_vals = {
                'account_id': receivable_account.id,
                'partner_id': invoice_partner.id,  # Invoice customer debt is cleared
                'debit': 0.0,
                'credit': amount_company_currency,
                'amount_currency': -allocate_amount,
                'currency_id': currency.id,
            }
        else:
            # For company currency, don't use amount_currency
            debit_line_vals = {
                'account_id': receivable_account.id,
                'partner_id': self.paying_partner_id.id,  # Paying customer gets the debt
                'debit': amount_company_currency,
                'credit': 0.0,
            }
            credit_line_vals = {
                'account_id': receivable_account.id,
                'partner_id': invoice_partner.id,  # Invoice customer debt is cleared
                'debit': 0.0,
                'credit': amount_company_currency,
            }
        
        # Create clearing journal entry
        move_vals = {
            'journal_id': self.journal_id.id,
            'date': self.payment_date,
            'ref': _('Clearing: %s - %s') % (self.paying_partner_id.name, invoice_partner.name),
            'is_clearing_entry': True,
            'clearing_payment_id': payment.id,
            'line_ids': [
                (0, 0, debit_line_vals),
                (0, 0, credit_line_vals),
            ],
        }
        
        _logger.info('Move Vals: %s', move_vals)
        _logger.info('Debit Line: %s', debit_line_vals)
        _logger.info('Credit Line: %s', credit_line_vals)
        
        clearing_move = self.env['account.move'].create(move_vals)
        clearing_move.action_post()
        
        # Reconcile invoice with clearing entry
        # Invoice has debit AR (customer owes us)
        # Clearing has credit AR (customer debt is cleared)
        invoice_line = invoice.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable'
            and not l.reconciled
            and l.amount_residual != 0
        )
        clearing_credit_line = clearing_move.line_ids.filtered(
            lambda l: l.partner_id == invoice_partner and l.credit > 0
        )
        
        _logger.info('Invoice line: %s (debit: %s, credit: %s, partner: %s)', 
                     invoice_line.ids if invoice_line else None,
                     sum(invoice_line.mapped('debit')) if invoice_line else 0,
                     sum(invoice_line.mapped('credit')) if invoice_line else 0,
                     invoice_line.mapped('partner_id.name') if invoice_line else None)
        _logger.info('Clearing credit line: %s (debit: %s, credit: %s, partner: %s)',
                     clearing_credit_line.ids if clearing_credit_line else None,
                     sum(clearing_credit_line.mapped('debit')) if clearing_credit_line else 0,
                     sum(clearing_credit_line.mapped('credit')) if clearing_credit_line else 0,
                     clearing_credit_line.mapped('partner_id.name') if clearing_credit_line else None)
        
        if invoice_line and clearing_credit_line:
            # Auto reconcile invoice with clearing entry to mark as paid
            lines_to_reconcile = invoice_line | clearing_credit_line
            lines_to_reconcile.reconcile()
            
            # Mark as clearing reconcile
            partial_reconciles = invoice_line.matched_debit_ids | invoice_line.matched_credit_ids
            partial_reconciles |= clearing_credit_line.matched_debit_ids | clearing_credit_line.matched_credit_ids
            partial_reconciles.filtered(lambda r: not r.is_clearing_reconcile).write({
                'is_clearing_reconcile': True,
                'clearing_payment_id': payment.id,
            })
        
        # Reconcile payment with clearing entry
        # Payment has debit AR (we received money, customer debt increases)
        # Clearing has debit AR (paying customer takes on the debt)
        payment_line = payment.move_id.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable'
            and not l.reconciled
            and l.amount_residual != 0
        )
        clearing_debit_line = clearing_move.line_ids.filtered(
            lambda l: l.partner_id == self.paying_partner_id and l.debit > 0
        )
        
        _logger.info('Payment line: %s (debit: %s, credit: %s, partner: %s)',
                     payment_line.ids if payment_line else None,
                     sum(payment_line.mapped('debit')) if payment_line else 0,
                     sum(payment_line.mapped('credit')) if payment_line else 0,
                     payment_line.mapped('partner_id.name') if payment_line else None)
        _logger.info('Clearing debit line: %s (debit: %s, credit: %s, partner: %s)',
                     clearing_debit_line.ids if clearing_debit_line else None,
                     sum(clearing_debit_line.mapped('debit')) if clearing_debit_line else 0,
                     sum(clearing_debit_line.mapped('credit')) if clearing_debit_line else 0,
                     clearing_debit_line.mapped('partner_id.name') if clearing_debit_line else None)
        
        if payment_line and clearing_debit_line:
            # Auto reconcile payment with clearing entry
            lines_to_reconcile = payment_line | clearing_debit_line
            lines_to_reconcile.reconcile()
            
            # Mark as clearing reconcile
            partial_reconciles = payment_line.matched_debit_ids | payment_line.matched_credit_ids
            partial_reconciles |= clearing_debit_line.matched_debit_ids | clearing_debit_line.matched_credit_ids
            partial_reconciles.filtered(lambda r: not r.is_clearing_reconcile).write({
                'is_clearing_reconcile': True,
                'clearing_payment_id': payment.id,
            })
        
        # Create clearing link
        self.env['buz.clearing.link'].create({
            'payment_id': payment.id,
            'clearing_move_id': clearing_move.id,
            'invoice_id': invoice.id,
            'amount': allocate_amount,
            'date': self.payment_date,
        })
    
    def _reconcile_credit_note_same_customer(self, payment, credit_line):
        """Reconcile credit note with payment for same customer (no clearing entry needed)"""
        import logging
        _logger = logging.getLogger(__name__)
        
        credit_note = credit_line.credit_note_id
        use_amount = credit_line.use_amount
        
        _logger.info('Reconciling credit note %s with payment (same customer)', credit_note.name)
        
        # Find UNRECONCILED receivable lines only
        credit_note_line = credit_note.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable' 
            and l.partner_id == self.paying_partner_id
            and not l.reconciled
            and l.amount_residual != 0
        )
        payment_line = payment.move_id.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable' 
            and l.partner_id == self.paying_partner_id
            and not l.reconciled
            and l.amount_residual != 0
        )
        
        _logger.info('Credit note line found: %s (reconciled: %s, residual: %s)', 
                     credit_note_line.ids if credit_note_line else None,
                     credit_note_line.reconciled if credit_note_line else None,
                     credit_note_line.amount_residual if credit_note_line else None)
        _logger.info('Payment line found: %s (reconciled: %s, residual: %s)', 
                     payment_line.ids if payment_line else None,
                     payment_line.reconciled if payment_line else None,
                     payment_line.amount_residual if payment_line else None)
        
        if not credit_note_line:
            raise UserError(
                _('Credit Note %s has no unreconciled receivable lines available. '
                  'It may have been fully reconciled already.') % credit_note.name
            )
        
        if not payment_line:
            raise UserError(
                _('Payment has no unreconciled receivable lines available for partner %s. '
                  'The payment amount may have been fully allocated already.') % self.paying_partner_id.name
            )
        
        if credit_note_line and payment_line:
            # Check residual amounts
            total_credit_residual = abs(sum(credit_note_line.mapped('amount_residual')))
            total_payment_residual = abs(sum(payment_line.mapped('amount_residual')))
            
            if total_credit_residual < use_amount:
                raise UserError(
                    _('Credit Note %s only has %.2f available (requested: %.2f)') 
                    % (credit_note.name, total_credit_residual, use_amount)
                )
            
            if total_payment_residual < use_amount:
                raise UserError(
                    _('Payment only has %.2f available for reconciliation (requested: %.2f)') 
                    % (total_payment_residual, use_amount)
                )
            
            # Reconcile credit note with payment
            lines_to_reconcile = credit_note_line | payment_line
            lines_to_reconcile.reconcile()
            
            # Mark as clearing reconcile
            partial_reconciles = credit_note_line.matched_debit_ids | credit_note_line.matched_credit_ids
            partial_reconciles |= payment_line.matched_debit_ids | payment_line.matched_credit_ids
            partial_reconciles.filtered(lambda r: not r.is_clearing_reconcile).write({
                'is_clearing_reconcile': True,
                'clearing_payment_id': payment.id,
            })
            
            # Create clearing link
            self.env['buz.clearing.link'].create({
                'payment_id': payment.id,
                'invoice_id': credit_note.id,
                'amount': use_amount,
                'date': self.payment_date,
            })
        else:
            _logger.warning('Could not find unreconciled receivable lines for credit note reconciliation. Credit Note may be fully reconciled or payment line not available.')
    
    def _create_credit_note_clearing_entry(self, payment, credit_line):
        """Create clearing journal entry for credit note (different customer - transfer credit to paying customer)"""
        credit_note = credit_line.credit_note_id
        credit_note_partner = credit_line.credit_note_partner_id
        use_amount = credit_line.use_amount
        currency = credit_line.currency_id
        
        import logging
        _logger = logging.getLogger(__name__)
        _logger.info('='*80)
        _logger.info('_create_credit_note_clearing_entry called')
        _logger.info('Credit Note: %s', credit_note.name)
        _logger.info('Credit Note Partner: %s (ID: %s)', credit_note_partner.name, credit_note_partner.id)
        _logger.info('Paying Partner: %s (ID: %s)', self.paying_partner_id.name, self.paying_partner_id.id)
        _logger.info('Use Amount: %s (type: %s)', use_amount, type(use_amount))
        _logger.info('Currency: %s (ID: %s)', currency.name if currency else 'None', currency.id if currency else 'None')
        
        # Validate use amount
        if not use_amount or use_amount <= 0:
            raise UserError(_('Use amount must be greater than 0 for credit note %s') % credit_note.name)
        
        # Get accounts
        receivable_account = credit_note.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable'
        ).account_id
        
        if not receivable_account:
            raise UserError(_('Cannot find receivable account for credit note %s') % credit_note.name)
        
        # Determine if we're using foreign currency
        company_currency = self.env.company.currency_id
        is_foreign_currency = currency != company_currency
        
        # Calculate amounts in company currency
        if is_foreign_currency:
            amount_company_currency = currency._convert(
                use_amount,
                company_currency,
                self.env.company,
                self.payment_date or fields.Date.today()
            )
        else:
            amount_company_currency = use_amount
        
        if not amount_company_currency or amount_company_currency <= 0:
            raise UserError(_('Invalid amount calculation for credit note %s. Amount: %s') % (credit_note.name, amount_company_currency))
        
        _logger.info('Amount Company Currency: %s', amount_company_currency)
        _logger.info('Is Foreign Currency: %s', is_foreign_currency)
        
        # Credit Note accounting logic:
        # Credit Note has Cr AR (we owe customer, customer has credit)
        # We need to:
        # Dr AR : Credit Note Partner (clear the credit we owe them)
        # Cr AR : Paying Partner (transfer the credit to paying partner)
        
        # Prepare line values based on currency
        if is_foreign_currency:
            debit_line_vals = {
                'account_id': receivable_account.id,
                'partner_id': credit_note_partner.id,  # Credit note customer's credit is cleared
                'debit': amount_company_currency,
                'credit': 0.0,
                'amount_currency': use_amount,
                'currency_id': currency.id,
            }
            credit_line_vals = {
                'account_id': receivable_account.id,
                'partner_id': self.paying_partner_id.id,  # Paying customer receives the credit
                'debit': 0.0,
                'credit': amount_company_currency,
                'amount_currency': -use_amount,
                'currency_id': currency.id,
            }
        else:
            debit_line_vals = {
                'account_id': receivable_account.id,
                'partner_id': credit_note_partner.id,
                'debit': amount_company_currency,
                'credit': 0.0,
            }
            credit_line_vals = {
                'account_id': receivable_account.id,
                'partner_id': self.paying_partner_id.id,
                'debit': 0.0,
                'credit': amount_company_currency,
            }
        
        # Create clearing journal entry
        move_vals = {
            'journal_id': self.journal_id.id,
            'date': self.payment_date,
            'ref': _('Credit Note Clearing: %s - %s') % (credit_note_partner.name, self.paying_partner_id.name),
            'is_clearing_entry': True,
            'clearing_payment_id': payment.id,
            'line_ids': [
                (0, 0, debit_line_vals),
                (0, 0, credit_line_vals),
            ],
        }
        
        _logger.info('Move Vals: %s', move_vals)
        _logger.info('Debit Line: %s', debit_line_vals)
        _logger.info('Credit Line: %s', credit_line_vals)
        
        clearing_move = self.env['account.move'].create(move_vals)
        clearing_move.action_post()
        
        # Reconcile credit note with clearing entry
        # Credit Note has credit AR (we owe customer)
        # Clearing has debit AR (clear the debt we owe)
        # Only reconcile UNRECONCILED lines
        credit_note_line = credit_note.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable'
            and l.partner_id == credit_note_partner
            and not l.reconciled
            and l.amount_residual != 0
        )
        clearing_debit_line = clearing_move.line_ids.filtered(
            lambda l: l.partner_id == credit_note_partner 
            and l.debit > 0
            and not l.reconciled
        )
        
        _logger.info('Credit Note line: %s (debit: %s, credit: %s, partner: %s, reconciled: %s, residual: %s)', 
                     credit_note_line.ids if credit_note_line else None,
                     sum(credit_note_line.mapped('debit')) if credit_note_line else 0,
                     sum(credit_note_line.mapped('credit')) if credit_note_line else 0,
                     credit_note_line.mapped('partner_id.name') if credit_note_line else None,
                     credit_note_line.reconciled if credit_note_line else None,
                     credit_note_line.amount_residual if credit_note_line else None)
        _logger.info('Clearing debit line: %s (debit: %s, credit: %s, partner: %s, reconciled: %s)',
                     clearing_debit_line.ids if clearing_debit_line else None,
                     sum(clearing_debit_line.mapped('debit')) if clearing_debit_line else 0,
                     sum(clearing_debit_line.mapped('credit')) if clearing_debit_line else 0,
                     clearing_debit_line.mapped('partner_id.name') if clearing_debit_line else None,
                     clearing_debit_line.reconciled if clearing_debit_line else None)
        
        if not credit_note_line:
            raise UserError(
                _('Credit Note %s has no unreconciled receivable lines available for partner %s. '
                  'It may have been fully reconciled already.') % (credit_note.name, credit_note_partner.name)
            )
        
        if credit_note_line and clearing_debit_line:
            # Auto reconcile credit note with clearing entry
            lines_to_reconcile = credit_note_line | clearing_debit_line
            lines_to_reconcile.reconcile()
            
            # Mark as clearing reconcile
            partial_reconciles = credit_note_line.matched_debit_ids | credit_note_line.matched_credit_ids
            partial_reconciles |= clearing_debit_line.matched_debit_ids | clearing_debit_line.matched_credit_ids
            partial_reconciles.filtered(lambda r: not r.is_clearing_reconcile).write({
                'is_clearing_reconcile': True,
                'clearing_payment_id': payment.id,
            })
        else:
            _logger.warning('Could not reconcile credit note with clearing entry. Lines may be already reconciled or not found.')
        
        # Create clearing link for credit note
        self.env['buz.clearing.link'].create({
            'payment_id': payment.id,
            'clearing_move_id': clearing_move.id,
            'invoice_id': credit_note.id,
            'amount': use_amount,
            'date': self.payment_date,
        })