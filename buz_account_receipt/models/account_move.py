# -*- coding: utf-8 -*-

from odoo import models, api


class AccountMove(models.Model):
    _inherit = 'account.move'

    @api.depends('line_ids.amount_residual')
    def _compute_amount(self):
        """
        Override to consider invoices reconciled with Outstanding Receipts as fully paid.
        
        Standard Odoo considers Outstanding Receipts as "in_payment" status,
        but for our AR process, once reconciled with Outstanding Receipts,
        the invoice should be considered "paid" even before bank reconciliation.
        
        This behavior can be controlled via:
        Settings > Accounting > Configuration > Consider Outstanding Receipts as Paid
        """
        # Call parent method first
        super(AccountMove, self)._compute_amount()
        
        # Check if the feature is enabled
        ar_outstanding_as_paid = self.env['ir.config_parameter'].sudo().get_param(
            'buz_account_receipt.ar_outstanding_as_paid', 'True'
        ) == 'True'
        
        # If feature is disabled, use standard Odoo behavior
        if not ar_outstanding_as_paid:
            return
        
        # For customer invoices, check if reconciled with Outstanding Receipts
        for move in self:
            # Only process customer invoices/refunds that show "in_payment"
            if move.move_type not in ('out_invoice', 'out_refund'):
                continue
            
            if move.payment_state != 'in_payment':
                continue
            
            # Check if the receivable line is fully reconciled
            if move.amount_residual != 0:
                continue
            
            # Find the receivable line
            receivable_line = move.line_ids.filtered(
                lambda line: line.account_id.account_type == 'asset_receivable'
            )
            
            if not receivable_line:
                continue
            
            # If fully reconciled (amount_residual = 0), consider it paid
            # regardless of whether it's reconciled with Outstanding Receipts or Bank
            if receivable_line.reconciled and move.amount_residual == 0:
                # Check if any of the reconciled lines come from Outstanding Receipts account
                has_outstanding_reconcile = False
                
                # Check matched credits (for invoices - debit on receivable)
                for partial in receivable_line.matched_credit_ids:
                    credit_line = partial.credit_move_id
                    if credit_line and credit_line.account_id.account_type not in (
                        'asset_receivable', 'liability_payable'
                    ):
                        # This is reconciled with a payment account (Outstanding or Bank)
                        has_outstanding_reconcile = True
                        break
                
                # Check matched debits (for refunds - credit on receivable)
                if not has_outstanding_reconcile:
                    for partial in receivable_line.matched_debit_ids:
                        debit_line = partial.debit_move_id
                        if debit_line and debit_line.account_id.account_type not in (
                            'asset_receivable', 'liability_payable'
                        ):
                            # This is reconciled with a payment account
                            has_outstanding_reconcile = True
                            break
                
                # If reconciled with payment account (Outstanding or Bank) and residual = 0,
                # consider it paid
                if has_outstanding_reconcile:
                    move.payment_state = 'paid'
