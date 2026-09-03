# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    @api.depends('source_amount', 'source_amount_currency', 'source_currency_id', 'currency_id', 'group_payment')
    def _compute_amount(self):
        super()._compute_amount()
        for wizard in self:
            refund_pv_id = wizard.env.context.get('buz_customer_refund_pv_id')
            refund_pv = wizard.env['buz.customer.refund.pv'].browse(refund_pv_id).exists()
            if refund_pv:
                # อ่านยอดจาก Refund PV โดยตรง เพื่อไม่เชื่อค่าที่ผู้ใช้แก้ใน context
                wizard.amount = refund_pv.refund_amount
            elif wizard.env.context.get('force_amount'):
                # คงพฤติกรรมเดิมของ Payment Voucher/WHT
                wizard.amount = wizard.env.context.get('force_amount')

    def make_payments(self):
        """Route Refund PV away from the optional batch-payment implementation."""
        if not self.env.context.get('buz_customer_refund_pv_id'):
            return super().make_payments()

        self.ensure_one()
        # account_payment_batch_process เปลี่ยนปุ่มมาตรฐานให้เรียก make_payments
        # จึงล้าง allocation ของ batch แล้วกลับไปใช้ standard Odoo reconciliation
        if 'invoice_payments' in self._fields and self.invoice_payments:
            self.invoice_payments = [fields.Command.clear()]
        return self.with_context(batch=False).action_create_payments()

    def _create_payments(self):
        """Override to link created payments to voucher, voucher line and receipt if context provided"""
        # Validate Register Refund Payment: payment amount must equal refund_amount (only for new button) and not exceed residual
        refund_pv_id = self._context.get('buz_customer_refund_pv_id')
        if refund_pv_id:
            refund_pv = self.env['buz.customer.refund.pv'].browse(refund_pv_id).exists()
            if not refund_pv:
                raise UserError(_("Customer Refund PV was not found."))
            if refund_pv.state != 'posted':
                raise UserError(_("Refund PV must be posted before Register Payment."))
            if refund_pv.payment_ids.filtered(lambda payment: payment.state != 'cancel'):
                raise UserError(_("Payment already registered for Refund PV %s.") % refund_pv.name)

            credit_note = refund_pv.credit_note_id
            if not credit_note or credit_note.state != 'posted' or credit_note.move_type != 'out_refund':
                raise UserError(_("A posted Customer Credit Note is required."))

            residual = abs(credit_note.amount_residual)
            for wizard in self:
                if refund_pv.currency_id.compare_amounts(wizard.amount, 0.0) <= 0:
                    raise UserError(_("Payment amount must be greater than 0."))
                if refund_pv.currency_id.compare_amounts(wizard.amount, refund_pv.refund_amount) != 0:
                    raise UserError(_("Payment amount (%.2f) must equal Refund Amount (%.2f).") % (wizard.amount, refund_pv.refund_amount))
                if refund_pv.currency_id.compare_amounts(wizard.amount, residual) > 0:
                    raise UserError(_("Payment amount (%.2f) exceeds remaining balance of Credit Note %s (%.2f).") % (wizard.amount, credit_note.name, residual))
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

        # Customer Refund PV: link payment to PV (Register Payment phase, no WHT/Bank Fee)
        refund_pv_id = self._context.get('buz_customer_refund_pv_id')
        if refund_pv_id and payments:
            refund_pv = self.env['buz.customer.refund.pv'].browse(refund_pv_id)
            if refund_pv.exists():
                # Link PV ↔ Payments (Many2many + Many2one)
                refund_pv.write({'payment_ids': [(4, p.id) for p in payments]})
                payments.write({'buz_customer_refund_pv_id': refund_pv.id})
                refund_pv.message_post(body=_("Payment %s registered for refund amount %.2f") % (', '.join(payments.mapped('name')), refund_pv.refund_amount))
                _logger.info("Linked %d payment(s) to customer refund PV %s", len(payments), refund_pv.name)
                # Standard Odoo already reconciles payment with source Credit Note via super, no extra WHT/Bank Fee in this phase
        
        return payments
