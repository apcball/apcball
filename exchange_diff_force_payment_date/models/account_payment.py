# -*- coding: utf-8 -*-

from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class AccountPayment(models.Model):
    """
    Extend account.payment to ensure exchange rate is fetched 
    from payment date, NOT from today's date
    """
    _inherit = 'account.payment'

    def _seek_for_lines(self):
        """
        Override to force Odoo to use exchange rate from payment date
        instead of current date (today).
        
        Problem:
        - When registering a payment with past date (e.g., 24/12/2025)
        - Odoo fetches exchange rate from TODAY instead of 24/12/2025
        - This causes wrong amount calculations
        
        Solution:
        - Force context with payment date before seeking lines
        """
        _logger.info('🔍 [PAYMENT] _seek_for_lines called for payment: %s | Date: %s', 
                     self.name or 'New', self.date)
        
        # Force the currency rate computation to use payment date
        # by adding it to context
        if self.date:
            self = self.with_context(date=self.date)
            _logger.info('✅ [PAYMENT] Forced context date to: %s', self.date)
        
        return super()._seek_for_lines()
    
    def _synchronize_from_moves(self, changed_fields):
        """
        Override to maintain payment date context when synchronizing
        """
        if self.date:
            self = self.with_context(date=self.date)
        return super()._synchronize_from_moves(changed_fields)


class AccountMoveLine(models.Model):
    """
    Extend account.move.line to use payment date for exchange rate calculation
    """
    _inherit = 'account.move.line'
    
    @api.depends('amount_currency', 'currency_id', 'company_id', 'move_id.date')
    def _compute_currency_rate(self):
        """
        Override to ensure exchange rate is computed using move date
        (which should be payment date for payments)
        
        Standard Odoo sometimes uses 'today' instead of move.date
        We force it to ALWAYS use move.date
        """
        for line in self:
            # Check if this is a payment move
            if line.move_id and line.move_id.payment_id:
                payment_date = line.move_id.date
                _logger.debug('🔍 [LINE] Computing currency rate for payment line | Move Date: %s', payment_date)
                
                # Force computation with payment date in context
                line_with_date = line.with_context(date=payment_date)
                super(AccountMoveLine, line_with_date)._compute_currency_rate()
            else:
                # Standard computation for non-payment lines
                super(AccountMoveLine, line)._compute_currency_rate()


class AccountMove(models.Model):
    """
    Extend account.move to ensure payment moves use correct date for rates
    """
    _inherit = 'account.move'
    
    def _recompute_dynamic_lines(self, recompute_all_taxes=False, recompute_tax_base_amount=False):
        """
        Override to ensure payment date is used when recomputing amounts
        """
        # For payment moves, force context with move date
        if self.payment_id and self.date:
            self = self.with_context(date=self.date)
            _logger.debug('🔍 [MOVE] Recomputing with forced date: %s for payment: %s', 
                         self.date, self.payment_id.name)
        
        return super()._recompute_dynamic_lines(recompute_all_taxes, recompute_tax_base_amount)
    
    @api.model
    def _get_accounting_date(self, invoice_date, has_tax):
        """
        Override to ensure payment accounting date uses payment date
        """
        # Check if we're in payment context
        if self.env.context.get('date'):
            return self.env.context.get('date')
        
        return super()._get_accounting_date(invoice_date, has_tax)


class AccountPaymentRegister(models.TransientModel):
    """
    Extend payment register wizard to ensure payment date is passed to context
    """
    _inherit = 'account.payment.register'
    
    @api.depends('source_amount', 'source_amount_currency', 'source_currency_id', 
                 'company_id', 'currency_id', 'payment_date')
    def _compute_amount(self):
        """
        Override to use payment_date for exchange rate lookup
        """
        for wizard in self:
            if wizard.payment_date:
                _logger.info('🔍 [WIZARD] Computing amount with payment_date: %s', wizard.payment_date)
                wizard_with_date = wizard.with_context(date=wizard.payment_date)
                super(AccountPaymentRegister, wizard_with_date)._compute_amount()
            else:
                super(AccountPaymentRegister, wizard)._compute_amount()
    
    def _create_payments(self):
        """
        Override to ensure payment date context is set when creating payments
        """
        _logger.info('🚀 [WIZARD] Creating payments with date: %s', self.payment_date)
        
        # Force payment date into context
        if self.payment_date:
            self = self.with_context(date=self.payment_date)
        
        return super()._create_payments()
    
    def _init_payments(self, to_process, edit_mode=False):
        """
        Override to maintain payment date in context
        """
        if self.payment_date:
            self = self.with_context(date=self.payment_date)
        
        return super()._init_payments(to_process, edit_mode)
