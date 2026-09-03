# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    @api.model_create_multi
    def create(self, vals_list):
        """บังคับยอด CV ตั้งแต่สร้าง wizard เพื่อป้องกันการแก้ค่าผ่าน RPC."""
        cv_id = self.env.context.get('buz_customer_refund_voucher_id')
        if cv_id:
            cv = self.env['buz.customer.refund.voucher'].browse(cv_id)
            if cv.exists() and cv.state == 'confirmed':
                cv.check_access_rights('read')
                cv.check_access_rule('read')
                for vals in vals_list:
                    vals['amount'] = cv.refund_amount
                    # account_payment_batch_process makes this field required.
                    if 'cheque_amount' in self._fields:
                        vals['cheque_amount'] = cv.refund_amount
        return super().create(vals_list)

    @api.depends('source_amount', 'source_amount_currency', 'source_currency_id', 'currency_id', 'group_payment')
    def _compute_amount(self):
        super()._compute_amount()
        for wizard in self:
            # Check if we have a forced amount from context (e.g. from Payment Voucher WHT)
            if self._context.get('force_amount') and not self._context.get('buz_customer_refund_voucher_id'):
                wizard.amount = self._context.get('force_amount')
            # CV context: force amount from voucher (server side, not client editable)
            if self._context.get('buz_customer_refund_voucher_id'):
                try:
                    cv_id = self._context.get('buz_customer_refund_voucher_id')
                    cv = self.env['buz.customer.refund.voucher'].browse(cv_id)
                    if cv.exists() and cv.state == 'confirmed':
                        wizard.amount = cv.refund_amount
                except Exception:
                    pass

    def _is_cv_context(self):
        cv_id = self._context.get('buz_customer_refund_voucher_id')
        if not cv_id:
            return False
        try:
            cv = self.env['buz.customer.refund.voucher'].browse(cv_id)
            if not cv.exists():
                return False
            # check access and state
            cv.check_access_rights('read')
            cv.check_access_rule('read')
            if cv.state != 'confirmed':
                return False
            return True
        except Exception:
            return False

    def _get_cv(self):
        cv_id = self._context.get('buz_customer_refund_voucher_id')
        if not cv_id:
            return self.env['buz.customer.refund.voucher'].browse()
        return self.env['buz.customer.refund.voucher'].browse(cv_id)

    def _create_payment_vals_from_wizard(self, batch_result):
        # CV-specific guard: enforce values from voucher, ignore client vals
        if self._is_cv_context():
            cv = self._get_cv()
            vals = super()._create_payment_vals_from_wizard(batch_result)
            # enforce company, partner, amount, journal, payment_type, etc.
            vals.update({
                'amount': cv.refund_amount,
                'partner_id': cv.partner_id.id,
                'partner_type': 'customer',
                'payment_type': 'outbound',
                'buz_customer_refund_voucher_id': cv.id,
                'ref': f"CV {cv.name}",
                'journal_id': cv.destination_journal_id.id if cv.destination_journal_id else vals.get('journal_id'),
            })
            # ensure currency is company currency
            vals['currency_id'] = cv.currency_id.id
            # for writeoff: if CV writeoff, the super handling of payment_difference etc will already set writeoff vals via wizard fields
            return vals
        return super()._create_payment_vals_from_wizard(batch_result)

    def _create_payment_vals_from_batch(self, batch_result):
        if self._is_cv_context():
            cv = self._get_cv()
            vals = super()._create_payment_vals_from_batch(batch_result)
            vals.update({
                'amount': cv.refund_amount,
                'partner_id': cv.partner_id.id,
                'partner_type': 'customer',
                'payment_type': 'outbound',
                'buz_customer_refund_voucher_id': cv.id,
                'ref': f"CV {cv.name}",
            })
            return vals
        return super()._create_payment_vals_from_batch(batch_result)

    def _create_payments(self):
        """Override to link created payments to voucher, voucher line and receipt if context provided"""
        # CV-specific validation before super
        if self._is_cv_context():
            cv = self._get_cv()
            # access and state already checked
            # lock credit note row for concurrency
            self.env.cr.execute("SELECT id FROM account_move WHERE id=%s FOR UPDATE", (cv.credit_note_id.id,))
            # residual check
            cn = cv.credit_note_id
            residual = abs(cn.amount_residual_signed) if hasattr(cn, 'amount_residual_signed') else abs(cn.amount_residual)
            residual = cv.currency_id.round(residual) if cv.currency_id else residual
            refund = cv.currency_id.round(cv.refund_amount) if cv.currency_id else cv.refund_amount
            if refund <= 0:
                raise UserError(_("Refund amount must be > 0."))
            if refund - residual > 0.005:
                raise UserError(_("Refund amount exceeds credit note residual (%.2f).") % residual)
            # company/currency checks
            if cn.company_id != cv.company_id:
                raise UserError(_("Company mismatch."))
            if cv.currency_id != cv.company_id.currency_id:
                raise UserError(_("Only company currency allowed."))
            # journal/method check
            if cv.destination_journal_id and cv.destination_journal_id.company_id != cv.company_id:
                raise UserError(_("Journal company mismatch."))
            # writeoff validation already in CV model, but re-check
            if cv.difference_handling == 'writeoff' and cv.difference_amount > 0.005:
                if not cv.writeoff_account_id or not cv.writeoff_reason:
                    raise UserError(_("Write-off account/reason required."))
                if cv.writeoff_account_id.company_id != cv.company_id:
                    raise UserError(_("Write-off account company mismatch."))
            # enforce wizard fields server side before super
            for wiz in self:
                wiz.amount = cv.refund_amount
                if cv.destination_journal_id:
                    wiz.journal_id = cv.destination_journal_id
                if cv.payment_method_line_id:
                    wiz.payment_method_line_id = cv.payment_method_line_id
                # handle difference handling
                if cv.difference_handling == 'keep_open':
                    wiz.payment_difference_handling = 'open'
                    wiz.writeoff_account_id = False
                    wiz.writeoff_label = False
                else:
                    # if full refund, handling irrelevant but set reconcile for writeoff case
                    if cv.difference_amount > 0.005:
                        wiz.payment_difference_handling = 'reconcile'
                        wiz.writeoff_account_id = cv.writeoff_account_id
                        wiz.writeoff_label = cv.writeoff_reason or "Write Off"
                    else:
                        wiz.payment_difference_handling = 'open'
                # clear WHT/bank charge if fields exist
                if 'wht_tax_id' in wiz._fields:
                    wiz.wht_tax_id = False
                if 'bank_charge' in wiz._fields:
                    wiz.bank_charge = 0
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

        # CV linking - must propagate failures (no swallow)
        if self._context.get('buz_customer_refund_voucher_id') and payments:
            cv_id = self._context.get('buz_customer_refund_voucher_id')
            cv = self.env['buz.customer.refund.voucher'].browse(cv_id)
            if cv.exists():
                # ensure payments are linked (if not already via vals)
                for p in payments:
                    if not p.buz_customer_refund_voucher_id:
                        p.write({'buz_customer_refund_voucher_id': cv.id})
                # validate payment belongs to CV and credit note
                for p in payments:
                    if p.buz_customer_refund_voucher_id != cv:
                        raise UserError(_("Payment voucher linkage mismatch."))
                    # check that payment is outbound customer
                    if p.payment_type != 'outbound' or p.partner_type != 'customer':
                        raise UserError(_("Payment must be outbound customer."))
                    if p.partner_id.commercial_partner_id != cv.partner_id.commercial_partner_id:
                        raise UserError(_("Payment partner mismatch."))
                # Chatter will be added by wizard; add safety log
                _logger.info("Linked %d payment(s) to CV %s", len(payments), cv.name)
        
        return payments
