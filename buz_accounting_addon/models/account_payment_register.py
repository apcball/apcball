# -*- coding: utf-8 -*-
from odoo import api, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare


class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

    @api.depends("source_amount", "source_amount_currency", "source_currency_id", "currency_id", "group_payment")
    def _compute_amount(self):
        super()._compute_amount()
        if self.env.context.get("force_amount"):
            for wizard in self:
                wizard.amount = self.env.context["force_amount"]
        cv = self._get_cv_from_context()
        if cv and cv.state == "confirmed":
            for wizard in self:
                wizard.amount = cv.refund_amount
                difference = cv.other_income_dis
                if float_compare(difference, 0.0, precision_rounding=cv.currency_id.rounding) > 0:
                    if cv.adjustment_method != "writeoff":
                        raise ValidationError(_("A partial refund must use Adjustment / Write-off."))
                    if not cv.other_income_account_id:
                        raise ValidationError(_("Select an Adjustment / Write-off Account."))
                    if not cv.refund_reason or not cv.refund_reason.strip():
                        raise ValidationError(_("Adjustment / Write-off Reason is required."))
                    wizard.payment_difference_handling = "reconcile"
                    wizard.writeoff_account_id = cv.other_income_account_id
                    wizard.writeoff_label = cv.refund_reason
                else:
                    wizard.payment_difference_handling = "open"
                    wizard.writeoff_account_id = False
                    wizard.writeoff_label = False

    @api.depends("journal_id", "available_partner_bank_ids")
    def _compute_partner_bank_id(self):
        super()._compute_partner_bank_id()
        cv = self._get_cv_from_context()
        if cv and cv.partner_bank_id:
            for wizard in self:
                if cv.partner_bank_id in wizard.available_partner_bank_ids:
                    wizard.partner_bank_id = cv.partner_bank_id
    def _get_cv_from_context(self):
        cv_id = self.env.context.get("buz_cv_id")
        return self.env["buz.customer.refund.voucher"].browse(cv_id).exists() if cv_id else self.env["buz.customer.refund.voucher"]

    def _create_payments(self):
        cv = self._get_cv_from_context()
        if cv:
            cv.ensure_one()
            cv._validate_for_register()
            existing = self.env["account.payment"].search([
                ("buz_customer_refund_voucher_id", "=", cv.id),
                ("state", "!=", "cancel"),
            ], limit=1)
            if existing:
                raise UserError(_("A payment already exists for this CV."))
        # Standard Odoo creates, posts, and reconciles the payment.
        result = super()._create_payments()
        if cv:
            cn = cv.credit_note_id
            payments = cn._get_reconciled_payments().filtered(
                lambda payment: payment.journal_id == cv.destination_journal_id
                and payment.partner_id == cv.partner_id
                and not payment.buz_customer_refund_voucher_id
            )
            payment = payments.sorted("id", reverse=True)[:1]
            if not payment:
                raise UserError(_("The standard payment wizard did not return a payment for this CV."))
            payment.write({"buz_customer_refund_voucher_id": cv.id})
            cv.write({"payment_id": payment.id, "state": "registered"})
        return result
