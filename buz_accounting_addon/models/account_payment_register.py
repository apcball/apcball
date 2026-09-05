# -*- coding: utf-8 -*-

from odoo import models, api, _
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
                # ใช้ยอดที่อนุมัติบน Refund PV เป็นแหล่งข้อมูลเดียวของยอดจ่าย
                wizard.amount = refund_pv.refund_amount
            elif wizard.env.context.get('force_amount'):
                # คงพฤติกรรมเดิมของ Payment Voucher/WHT
                wizard.amount = wizard.env.context.get('force_amount')

    def make_payments(self):
        """หลีกเลี่ยง batch entry point เฉพาะ Refund PV แล้วใช้ standard register flow."""
        if not self.env.context.get('buz_customer_refund_pv_id'):
            return super().make_payments()
        return self.with_context(batch=False).action_create_payments()

    def _add_refund_pv_link(self, vals):
        refund_pv_id = self.env.context.get('buz_customer_refund_pv_id')
        if refund_pv_id:
            refund_pv = self.env['buz.customer.refund.pv'].browse(refund_pv_id).exists()
            if refund_pv:
                vals['buz_customer_refund_pv_id'] = refund_pv.id
        return vals

    def _create_payment_vals_from_wizard(self, batch_result):
        vals = super()._create_payment_vals_from_wizard(batch_result)
        return self._add_refund_pv_link(vals)

    def _create_payment_vals_from_batch(self, batch_result):
        vals = super()._create_payment_vals_from_batch(batch_result)
        return self._add_refund_pv_link(vals)

    def _validate_refund_pv(self):
        """ตรวจเงื่อนไข Refund PV ก่อนให้ Odoo สร้าง Post และ Reconcile payment."""
        refund_pv_id = self._context.get('buz_customer_refund_pv_id')
        if not refund_pv_id:
            return False

        refund_pv = self.env['buz.customer.refund.pv'].browse(refund_pv_id).exists()
        if not refund_pv:
            raise UserError(_("Customer Refund PV was not found."))
        if refund_pv.state != 'posted':
            raise UserError(_("Refund PV must be posted before Register Payment."))
        if refund_pv.payment_ids.filtered(lambda payment: payment.state != 'cancel'):
            raise UserError(_("Payment already registered for Refund PV %s.") % refund_pv.name)
        if refund_pv.bank_free_dis:
            raise UserError(_("Bank Fee cannot be posted until a Bank Fee Journal Entry is supported."))
        if refund_pv.other_income_dis > 0 and not refund_pv.other_income_account_id:
            raise UserError(_("Please select an Other Income Account when Other Income is greater than zero."))
        if refund_pv.other_income_account_id and (
            refund_pv.other_income_account_id.company_id != refund_pv.company_id
            or refund_pv.other_income_account_id.deprecated
        ):
            raise UserError(_("Other Income Account must be active and belong to the same company."))

        credit_note = refund_pv.credit_note_id
        if not credit_note or credit_note.state != 'posted' or credit_note.move_type != 'out_refund':
            raise UserError(_("A posted Customer Credit Note is required."))

        residual = abs(credit_note.amount_residual)
        expected_other_income = max(residual - refund_pv.refund_amount, 0.0)
        if refund_pv.currency_id.compare_amounts(
            refund_pv.other_income_dis, expected_other_income,
        ) != 0:
            raise UserError(_(
                "Credit Note residual changed. Please cancel and recreate/confirm "
                "the Refund PV before registering payment."
            ))
        for wizard in self:
            if refund_pv.currency_id.compare_amounts(wizard.amount, 0.0) <= 0:
                raise UserError(_("Payment amount must be greater than 0."))
            if refund_pv.currency_id.compare_amounts(wizard.amount, refund_pv.refund_amount) != 0:
                raise UserError(_("Payment amount (%.2f) must equal Refund Amount (%.2f).") % (wizard.amount, refund_pv.refund_amount))
            if refund_pv.currency_id.compare_amounts(wizard.amount, residual) > 0:
                raise UserError(_("Payment amount (%.2f) exceeds remaining balance of Credit Note %s (%.2f).") % (wizard.amount, credit_note.name, residual))

        # ตรวจซ้ำก่อน Register เพราะสถานะ Invoice อาจเปลี่ยนหลัง Confirm
        refund_pv._check_source_invoices_paid()
        return refund_pv

    def _create_payments(self):
        refund_pv = self._validate_refund_pv()
        # Odoo standard สร้าง Payment ตาม sequence, Post และ Reconcile กับ Credit Note
        payments = super()._create_payments()

        payment_voucher_id = self._context.get('buz_payment_voucher_id')
        if payment_voucher_id and payments:
            payment_voucher = self.env['account.payment.voucher'].browse(payment_voucher_id)
            if payment_voucher.exists():
                payments.write({'buz_payment_voucher_id': payment_voucher_id})
                paid_moves = payments.mapped('reconciled_bill_ids')
                for line in payment_voucher.line_ids:
                    line_payments = payments.filtered(
                        lambda payment: not paid_moves or line.move_id in payment.reconciled_bill_ids
                    ) or payments
                    line.write({'payment_ids': [(4, payment.id) for payment in line_payments]})
                payment_voucher.message_post(
                    body=_("Payment(s) %s created and linked to voucher") % ', '.join(payments.mapped('name'))
                )

        voucher_line_id = self._context.get('buz_voucher_line_id')
        receipt_id = self._context.get('buz_receipt_id')
        if voucher_line_id:
            voucher_line = self.env['account.receipt.voucher.line'].browse(voucher_line_id)
            if voucher_line.exists():
                voucher_line.write({'payment_ids': [(4, payment.id) for payment in payments]})
                if voucher_line.voucher_id:
                    voucher_line.voucher_id.message_post(
                        body=_("Payment(s) %s created and linked from RV line") % ', '.join(payments.mapped('name'))
                    )
        if receipt_id:
            receipt = self.env['account.receipt'].browse(receipt_id)
            if receipt.exists():
                receipt.write({'payment_ids': [(4, payment.id) for payment in payments]})
                receipt.message_post(
                    body=_("Payment(s) %s created from voucher") % ', '.join(payments.mapped('name'))
                )

        if voucher_line_id and payments:
            voucher_line = self.env['account.receipt.voucher.line'].browse(voucher_line_id)
            if voucher_line.exists() and voucher_line.voucher_id and voucher_line.receipt_id:
                invoices = voucher_line.receipt_id.line_ids.mapped('move_id').filtered(
                    lambda move: move.state == 'posted' and move.move_type in ('out_invoice', 'out_refund')
                )
                for payment in payments:
                    try:
                        voucher_line.voucher_id._reconcile_payment_with_invoices(payment, invoices)
                    except Exception as error:
                        _logger.warning("Failed to auto-reconcile payment %s: %s", payment.name, error)

        if refund_pv and payments:
            refund_pv.write({'payment_ids': [(4, payment.id) for payment in payments]})
            payments.write({'buz_customer_refund_pv_id': refund_pv.id})
            refund_pv.message_post(
                body=_("Payment %s registered for refund amount %.2f") % (
                    ', '.join(payments.mapped('name')), refund_pv.refund_amount
                )
            )
        return payments
