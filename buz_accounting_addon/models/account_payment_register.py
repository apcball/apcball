# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare
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
            cv_id = self._context.get("buz_cv_id")
            cv = self.env["buz.customer.refund.voucher"].browse(cv_id).exists() if cv_id else self.env["buz.customer.refund.voucher"]
            if cv and cv.state == "confirmed":
                cv.ensure_one()
                # CV เน€เธยเน€เธยเน€เธย Refund Amount เน€เธโ€”เน€เธเธ•เน€เธยเน€เธยเน€เธเธเน€เธยเน€เธยเน€เธยเน€เธยเน€เธเธเน€เธยเน€เธเธเน€เธเธเน€เธเธ‘เน€เธโ€ขเน€เธเธ” เน€เธยเน€เธเธเน€เธยเน€เธยเน€เธยเน€เธยเน€เธเธเน€เธเธเน€เธโ€ Residual เน€เธโ€”เน€เธเธ•เน€เธย wizard เน€เธโฌเน€เธโ€ขเน€เธเธ”เน€เธเธเน€เธยเน€เธเธเน€เธยเน€เธเธเน€เธเธ‘เน€เธโ€ขเน€เธยเน€เธยเน€เธเธเน€เธเธ‘เน€เธโ€ขเน€เธเธ”
                wizard.amount = cv.refund_amount
                difference = cv.other_income_dis
                if float_compare(difference, 0.0, precision_rounding=cv.currency_id.rounding) > 0:
                    if not cv.other_income_account_id:
                        raise ValidationError(_("Other Income Account is required for a partial refund."))
                    wizard.payment_difference_handling = "reconcile"
                    wizard.writeoff_account_id = cv.other_income_account_id
                    wizard.writeoff_label = _("Other Income")
                else:
                    # เน€เธยเน€เธยเน€เธเธ’เน€เธเธเน€เธโฌเน€เธโ€ขเน€เธยเน€เธเธ CN เน€เธโ€ขเน€เธยเน€เธเธเน€เธยเน€เธยเน€เธเธเน€เธยเน€เธเธเน€เธเธ•เน€เธเธเน€เธเธ’เน€เธเธเน€เธยเน€เธเธ’เน€เธเธ Write-off
                    wizard.payment_difference_handling = "open"
                    wizard.writeoff_account_id = False
                    wizard.writeoff_label = False

    def _post_payments(self, to_process, edit_mode=False):
        """Check the CV payment move number before the standard post.

        Odoo assigns an ``account.move`` number while posting.  Reserving that
        number on the newly-created draft move lets us report a duplicate
        against the selected Payment Journal before ``action_post()`` runs.
        The override is intentionally limited to the CV context; Vendor PV and
        Receipt Voucher use the standard Odoo path unchanged.
        """
        cv_id = self._context.get("buz_cv_id")
        if cv_id:
            payments = self.env["account.payment"]
            for values in to_process:
                payments |= values.get("payment", self.env["account.payment"])
            cv = self.env["buz.customer.refund.voucher"].browse(cv_id).exists()
            if cv and cv.state == "confirmed":
                seen = set()
                for payment in payments:
                    move = payment.move_id
                    if move and move.state == "draft" and move.name in (False, "/"):
                        # This uses the selected journal's existing Odoo
                        # sequence; it does not modify journal configuration or
                        # any existing Journal Entry.
                        move._set_next_sequence()
                    if not move or move.name in (False, "/"):
                        continue
                    key = (move.company_id.id, move.journal_id.id, move.name)
                    if key in seen:
                        raise UserError(_(
                            "Duplicate Journal Entry number %s detected in the refund payment.",
                            move.name,
                        ))
                    seen.add(key)
                    duplicate = self.env["account.move"].search([
                        ("id", "!=", move.id),
                        ("company_id", "=", move.company_id.id),
                        ("journal_id", "=", move.journal_id.id),
                        ("name", "=", move.name),
                    ], limit=1)
                    if duplicate:
                        raise UserError(_(
                            "Duplicate Journal Entry number %s detected in Payment Journal %s.",
                            move.name,
                            move.journal_id.display_name,
                        ))
        return super()._post_payments(to_process, edit_mode=edit_mode)

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
                existing_payment = self.env["account.payment"].search(
                    [
                        ("buz_customer_refund_voucher_id", "=", cv.id),
                        ("state", "!=", "cancel"),
                    ],
                    limit=1,
                )
                if existing_payment:
                    raise UserError(_("A non-cancelled refund payment already exists for this CV."))
                cn = cv.credit_note_id
                residual = abs(cn.amount_residual_signed) if hasattr(cn, 'amount_residual_signed') and cn.amount_residual_signed is not None else abs(cn.amount_residual)
                if cv.refund_amount < 0.01:
                    from odoo.exceptions import UserError
                    raise UserError(_("Refund Amount must be greater than 0."))
                if cv.refund_amount - residual > 0.01:
                    from odoo.exceptions import UserError
                    raise UserError(_("Refund Amount (%.2f) cannot exceed Credit Note residual (%.2f).") % (cv.refund_amount, residual))
                expected_difference = max(residual - cv.refund_amount, 0.0)
                if float_compare(self.amount, cv.refund_amount, precision_rounding=cn.currency_id.rounding) != 0:
                    raise UserError(_("Payment amount does not match CV Refund Amount."))
                if float_compare(self.payment_difference, expected_difference, precision_rounding=cn.currency_id.rounding) != 0:
                    raise UserError(_("Payment difference does not match CN residual minus Refund Amount."))
                # Let super create payment, then post-process with transactional integrity
                try:
                    payments = super()._create_payments()
                except Exception as e:
                    # Rollback will be handled by Odoo transaction; ensure CV stays confirmed
                    _logger.error("CV %s Register Refund failed: %s", cv.name, e)
                    raise
                # Post: set backlink, ensure outbound, post if needed, reconcile
                if payments:
                    # The wizard context must produce a Customer Outbound Payment.
                    for p in payments:
                        if p.payment_type != "outbound" or p.partner_type != "customer":
                            raise UserError(_("Payment must be a Customer Outbound Payment."))
                    payments.write({'buz_customer_refund_voucher_id': cv.id})
                    # Post if draft
                    for p in payments:
                        if p.state == 'draft':
                            p.action_post()
                    # Odoo เน€เธเธเน€เธเธ’เน€เธโ€ขเน€เธเธเน€เธยเน€เธเธ’เน€เธย reconcile Payment เน€เธยเน€เธเธ…เน€เธเธ Write-off เน€เธยเน€เธเธ‘เน€เธย CN เน€เธยเน€เธเธ…เน€เธยเน€เธเธ
                    # เน€เธโ€ขเน€เธเธเน€เธเธเน€เธยเน€เธยเน€เธเธ…เน€เธเธ…เน€เธเธ‘เน€เธยเน€เธยเน€เธยเน€เธยเน€เธยเน€เธเธเน€เธยเน€เธโฌเน€เธยเน€เธเธ…เน€เธเธ•เน€เธยเน€เธเธเน€เธย CV เน€เธโฌเน€เธยเน€เธยเน€เธย Registered; เน€เธโ€“เน€เธยเน€เธเธ’เน€เธยเน€เธเธเน€เธยเน€เธเธเน€เธเธเน€เธยเน€เธเธเน€เธยเน€เธยเน€เธเธเน€เธย rollback transaction
                    cn.invalidate_recordset(["amount_residual", "amount_residual_signed", "payment_state"])
                    residual_after = abs(cn.amount_residual_signed) if cn.amount_residual_signed is not None else abs(cn.amount_residual)
                    if float_compare(residual_after, 0.0, precision_rounding=cn.currency_id.rounding) != 0:
                        raise UserError(_("Credit Note %s was not fully reconciled (residual %.2f).") % (cn.name, residual_after))
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
