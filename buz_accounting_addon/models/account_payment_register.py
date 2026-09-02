# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    @api.depends('source_amount', 'source_amount_currency', 'source_currency_id', 'currency_id', 'group_payment')
    def _compute_amount(self):
        super()._compute_amount()
        for wizard in self:
            # Check if we have a forced amount from context (e.g. from Payment Voucher WHT)
            if self._context.get('force_amount'):
                wizard.amount = self._context.get('force_amount')

    def _create_payments(self):
        """Override to link created payments to voucher, voucher line and receipt if context provided"""
        payments = super()._create_payments()
        
        # Link payments to payment voucher if context provided
        payment_voucher_id = self._context.get('buz_payment_voucher_id')
        if payment_voucher_id and payments:
            payment_voucher = self.env['account.payment.voucher'].browse(payment_voucher_id)
            if payment_voucher.exists():
                payments.write({'buz_payment_voucher_id': payment_voucher_id})
                # Link payments to the voucher lines whose bills they pay
                # (grouped payments cover every line of the voucher)
                paid_moves = payments.mapped('reconciled_bill_ids')
                for line in payment_voucher.line_ids:
                    line_payments = payments.filtered(
                        lambda p: not paid_moves or line.move_id in p.reconciled_bill_ids
                    ) or payments
                    line.write({
                        'payment_ids': [(4, payment.id) for payment in line_payments]
                    })
                payment_voucher.message_post(
                    body=_("Payment(s) %s created and linked to voucher") % ', '.join(payments.mapped('name'))
                )
                _logger.info("Linked %d payment(s) to payment voucher %s", len(payments), payment_voucher.name)

        # Check if we have voucher line or receipt context
        voucher_line_id = self._context.get('buz_voucher_line_id')
        receipt_id = self._context.get('buz_receipt_id')
        
        if voucher_line_id:
            voucher_line = self.env['account.receipt.voucher.line'].browse(voucher_line_id)
            if voucher_line.exists():
                # Link payments to voucher line
                voucher_line.write({
                    'payment_ids': [(4, payment.id) for payment in payments]
                })
                _logger.info("Linked %d payment(s) to voucher line %s" % (len(payments), voucher_line.id))
                
                # Add message to voucher
                if voucher_line.voucher_id:
                    payment_names = ', '.join(payments.mapped('name'))
                    voucher_line.voucher_id.message_post(
                        body=_("Payment(s) %s created and linked from RV line") % payment_names
                    )
        
        if receipt_id:
            receipt = self.env['account.receipt'].browse(receipt_id)
            if receipt.exists():
                # Link payments to receipt via M2M
                receipt.write({
                    'payment_ids': [(4, payment.id) for payment in payments]
                })
                _logger.info("Linked %d payment(s) to receipt %s" % (len(payments), receipt.name))
                
                # Add message to receipt
                payment_names = ', '.join(payments.mapped('name'))
                receipt.message_post(
                    body=_("Payment(s) %s created from voucher") % payment_names
                )
        
        # Auto-reconcile if we have the context
        if voucher_line_id and payments:
            voucher_line = self.env['account.receipt.voucher.line'].browse(voucher_line_id)
            if voucher_line.exists() and voucher_line.voucher_id:
                # Get all invoices from the receipt
                receipt = voucher_line.receipt_id
                if receipt:
                    invoices = receipt.line_ids.mapped('move_id').filtered(
                        lambda m: m.state == 'posted' and m.move_type in ('out_invoice', 'out_refund')
                    )
                    
                    # Try to reconcile each payment with invoices
                    for payment in payments:
                        try:
                            voucher_line.voucher_id._reconcile_payment_with_invoices(payment, invoices)
                            _logger.info("Auto-reconciled payment %s with invoices" % payment.name)
                        except Exception as e:
                            _logger.warning("Failed to auto-reconcile payment %s: %s" % (payment.name, str(e)))
        
        return payments
