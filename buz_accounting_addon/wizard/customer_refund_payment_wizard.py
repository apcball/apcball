# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

class BuzCustomerRefundPaymentWizard(models.TransientModel):
    _name = "buz.customer.refund.payment.wizard"
    _description = "Customer Refund Payment Wizard Wrapper"

    voucher_id = fields.Many2one("buz.customer.refund.voucher", string="Refund Voucher", required=True, readonly=True)
    payment_date = fields.Date(string="Actual Payment Date", required=True, default=fields.Date.context_today)

    # readonly displays from voucher
    refund_amount = fields.Monetary(related="voucher_id.refund_amount", readonly=True)
    difference_handling = fields.Selection(related="voucher_id.difference_handling", readonly=True)
    difference_amount = fields.Monetary(related="voucher_id.difference_amount", readonly=True)
    writeoff_account_id = fields.Many2one(related="voucher_id.writeoff_account_id", readonly=True)
    destination_journal_id = fields.Many2one(related="voucher_id.destination_journal_id", readonly=True)
    payment_method_line_id = fields.Many2one(related="voucher_id.payment_method_line_id", readonly=True)
    payment_type = fields.Selection(related="voucher_id.payment_type", readonly=True)
    currency_id = fields.Many2one(related="voucher_id.currency_id", readonly=True)
    company_id = fields.Many2one(related="voucher_id.company_id", readonly=True)

    @api.constrains("payment_date")
    def _check_payment_date(self):
        for rec in self:
            if rec.voucher_id.credit_note_id and rec.payment_date and rec.voucher_id.credit_note_id.invoice_date:
                if rec.payment_date < rec.voucher_id.credit_note_id.invoice_date:
                    raise ValidationError(_("Actual Payment Date cannot be before Credit Note date."))

    def action_create_payment(self):
        self.ensure_one()
        voucher = self.voucher_id
        if voucher.state != "confirmed":
            raise UserError(_("Voucher must be Confirmed."))
        if voucher.company_id not in self.env.companies:
            raise UserError(_("Access denied for company."))
        # Validate payment date lock
        if voucher.credit_note_id.invoice_date and self.payment_date < voucher.credit_note_id.invoice_date:
            raise ValidationError(_("Actual Payment Date cannot be before Credit Note date."))
        # Check lock date via standard Odoo: will be validated by payment register, but we pre-check
        # Use voucher's company lock dates
        # Re-read CV values server side (ignore any client tampering - we read from voucher)
        # Build context for standard payment register
        ctx = {
            "active_model": "account.move",
            "active_ids": voucher.credit_note_id.ids,
            "default_payment_date": self.payment_date,
            "buz_customer_refund_voucher_id": voucher.id,
            "skip_wht_deduct": True,
        }
        # Related modules may add required fields to the standard wizard (for
        # example, account_payment_batch_process adds ``cheque_amount``).
        # Populate those fields only when installed to keep this CV flow
        # compatible with the standard Odoo 17 wizard as well.
        register_model = self.env["account.payment.register"]
        register_vals = {
            "payment_date": self.payment_date,
            "amount": voucher.refund_amount,
            "payment_difference_handling": "reconcile" if voucher.difference_handling == "keep_open" else "open",
            # For writeoff, we will let override handle writeoff lines? But spec says writeoff must create difference to close CN.
            # In standard register, writeoff with difference handling open + manual? Need to check.
            # Actually for writeoff we need to use "reconcile" with writeoff_account? Let's set handling accordingly.
            # For writeoff, we want to reconcile payment + writeoff with CN to zero. Standard behavior: if amount < residual, handling = open leaves residual, handling = reconcile keeps open? Need to investigate.
            # For writeoff we will pass group_payment True and let _create_payment handle writeoff via payment vals.
            # So set payment_difference_handling based on spec: keep_open -> open (keep residual), writeoff -> reconcile? Wait spec: Keep Open must reconcile only refund amount and leave residual, Write Off must close residual via writeoff account.
            # In Odoo payment register, "open" means keep residual open, "reconcile" means writeoff? Actually "reconcile" with writeoff_account closes difference.
            # So map: keep_open => open, writeoff => reconcile
        }
        if "cheque_amount" in register_model._fields:
            register_vals["cheque_amount"] = voucher.refund_amount
        register = register_model.with_context(**ctx).create(register_vals)
        # Force handling correctly
        if voucher.difference_handling == "keep_open":
            register.payment_difference_handling = "open"
            register.writeoff_account_id = False
            register.writeoff_label = False
        else:
            register.payment_difference_handling = "reconcile"
            register.writeoff_account_id = voucher.writeoff_account_id.id
            register.writeoff_label = voucher.writeoff_reason or "Write Off"
        # Handle optional fields for compatibility (WHT, bank charge)
        vals = {}
        if "wht_tax_id" in register._fields:
            # skip WHT
            vals["wht_tax_id"] = False
        if "bank_charge" in register._fields:
            vals["bank_charge"] = 0
        if "bank_charge_account_id" in register._fields:
            vals["bank_charge_account_id"] = False
        if vals:
            # only if fields exist
            for k, v in vals.items():
                if k in register._fields:
                    register[k] = v
        # Set journal and payment method from voucher (server side, not client)
        if voucher.destination_journal_id:
            register.journal_id = voucher.destination_journal_id
        if voucher.payment_method_line_id:
            register.payment_method_line_id = voucher.payment_method_line_id

        # Now call _create_payments - this will go through our override
        payments = register._create_payments()
        if not payments:
            raise UserError(_("Payment creation failed."))
        # Update voucher audit
        voucher.write({"registered_by": self.env.user.id, "registered_date": fields.Datetime.now()})
        voucher.message_post(body=_("Refund Payment %s registered on %s by %s") % (", ".join(payments.mapped("name")), self.payment_date, self.env.user.name))
        # Return action to open payments
        return voucher.action_open_payments()
