# -*- coding: utf-8 -*-

from odoo import models, _, Command, api
from datetime import date as datetime_date
import logging

_logger = logging.getLogger(__name__)


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'
    
    def reconcile(self):
        """
        Override reconcile to track payment date for later use in EXCH entries
        """
        # Find payment moves BEFORE reconciliation
        payment_date = None
        
        for line in self:
            if line.move_id.payment_id:
                payment_date = line.move_id.date
                _logger.warning('🎯 Found payment in reconcile: %s | Date: %s', 
                              line.move_id.name, payment_date)
                break
        
        if not payment_date:
            # Check for bank/cash journal moves
            for line in self:
                if line.move_id.journal_id.type in ('bank', 'cash') and not line.move_id.is_invoice():
                    payment_date = line.move_id.date
                    _logger.warning('🎯 Found payment via journal: %s | Date: %s', 
                                  line.move_id.name, payment_date)
                    break
        
        # Store payment date in context for EXCH creation
        if payment_date:
            self = self.with_context(force_exchange_date=payment_date)
            _logger.warning('💾 Stored payment_date in context: %s', payment_date)
        
        return super().reconcile()

    def _prepare_exchange_difference_move_vals(self, amounts_list, company=None, exchange_date=None, **kwargs):
        """
        Override to force exchange difference move to use payment date
        from context that was set in reconcile()
        """
        _logger.warning('🚀 CUSTOM MODULE: exchange_diff_force_payment_date IS ACTIVE!')
        
        # Check if we have forced exchange date from context
        forced_date = self.env.context.get('force_exchange_date')
        if forced_date:
            _logger.warning('✅ Using forced exchange date from context: %s', forced_date)
            exchange_date = forced_date
        
        # Call standard Odoo logic
        result = super()._prepare_exchange_difference_move_vals(amounts_list, company, exchange_date, **kwargs)
        
        # If no exchange difference needed, return empty
        if not result or not result.get('move_values'):
            return result
        
        move_vals = result['move_values']
        
        # CRITICAL: Override the date AFTER super() call
        if forced_date:
            move_vals['date'] = forced_date
            _logger.warning('💰 EXCH move date set to payment date: %s', forced_date)
        
        return result

