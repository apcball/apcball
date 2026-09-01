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
        """Override to link created payments to voucher, voucher line and receipt if context provided.
        Also handles Customer Refund Voucher (CV) outbound payment creation + post + reconcile in one transaction.
        """
        # CV path: intercept before super to enforce validation and rollback on failure
        buz_cv_id = self._context.get('buz_cv_id')
        if buz_cv_id:
            # Early extension: ensure we don't alter non-CV flows
            cv = self.env['buz.customer.refund.voucher'].browse(buz_cv_id)
            if cv.exists() and cv.state == 'confirmed':
                # Validate CV still matches CN residual before creating payment
                cn = cv.credit_note_id
                residual = abs(cn.amount_residual_signed) if hasattr(cn, 'amount_residual_signed') and cn.amount_residual_signed is not None else abs(cn.amount_residual)
                if abs(cv.refund_amount - residual) > 0.01:
                    from odoo.exceptions import UserError
                    raise UserError(_("Refund Amount (%.2f) no longer matches Credit Note residual (%.2f).") % (cv.refund_amount, residual))
                # Let super create payment, then post-process with transactional integrity
                try:
                    payments = super()._create_payments()
                except Exception as e:
                    # Rollback will be handled by Odoo transaction; ensure CV stays confirmed
                    _logger.error("CV %s Register Refund failed: %s", cv.name, e)
                    raise
                # Post: set backlink, ensure outbound, post if needed, reconcile
                if payments:
                    # Enforce outbound customer payment
                    for p in payments:
                        if p.payment_type != 'outbound' or p.partner_type != 'customer':
                            _logger.warning("Correcting payment %s to outbound/customer for CV %s", p.name, cv.name)
                            p.write({'payment_type': 'outbound', 'partner_type': 'customer'})
                    payments.write({'buz_customer_refund_voucher_id': cv.id})
                    # Post if draft
                    for p in payments:
                        if p.state == 'draft':
                            p.action_post()
                    # Reconcile with credit note (asset_receivable line)
                    try:
                        # Find CV payment receivable line and CN receivable line
                        for p in payments:
                            p_move_lines = p.move_id.line_ids.filtered(lambda l: l.account_id.account_type == 'asset_receivable' and not l.reconciled)
                            cn_lines = cn.line_ids.filtered(lambda l: l.account_id.account_type == 'asset_receivable' and not l.reconciled)
                            # For out_refund, receivable line is credit; still same account
                            lines_to_rec = (p_move_lines + cn_lines).filtered(lambda l: not l.reconciled)
                            if len(lines_to_rec) > 1:
                                # ensure same account & partner before reconcile
                                accounts = lines_to_rec.mapped('account_id')
                                for acc in accounts:
                                    acc_lines = lines_to_rec.filtered(lambda l: l.account_id == acc)
                                    if len(acc_lines) > 1:
                                        acc_lines.reconcile()
                    except Exception as e:
                        _logger.error("CV %s reconcile failed: %s", cv.name, e)
                        raise UserError(_("Payment created but reconciliation failed: %s") % e)
                    # Mark CV registered only after successful reconcile
                    cv.write({'payment_id': payments[0].id, 'state': 'registered'})
                    cv.message_post(body=_("Refund Payment %s created, posted and reconciled.") % ', '.join(payments.mapped('name')))
                    payments.write({'ref': f"CV {cv.name}"})
                return payments
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
