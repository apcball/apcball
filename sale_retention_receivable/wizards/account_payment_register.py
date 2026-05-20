from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

    _RETENTION_ALLOWED_ACCOUNT_TYPES = ("asset_receivable", "asset_current")

    retention_enabled = fields.Boolean(string="Has Retention", readonly=True)
    retention_amount = fields.Monetary(string="Retention Amount", readonly=True,
                                       currency_field="currency_id")
    retention_account_id = fields.Many2one("account.account", string="Retention Account",
                                           domain="[('account_type', 'in', ('asset_receivable', 'asset_current'))]")

    @api.depends("line_ids")
    def _compute_retention_info(self):
        for wizard in self:
            invoice = wizard._get_invoice_from_lines()
            if invoice and invoice.retention_enabled and invoice.retention_amount:
                wizard.retention_enabled = True
                wizard.retention_amount = invoice.retention_amount
                account = invoice._get_retention_account()
                if account:
                    wizard.retention_account_id = account
            else:
                wizard.retention_enabled = False
                wizard.retention_amount = 0.0
                wizard.retention_account_id = False

    def _get_invoice_from_lines(self):
        """Get the single customer invoice being paid."""
        invoices = self.line_ids.move_id.filtered(
            lambda m: m.move_type == "out_invoice"
        )
        if len(invoices) == 1:
            return invoices
        return self.env["account.move"].browse()

    @api.onchange("retention_enabled", "retention_amount", "line_ids")
    def _onchange_retention_payment(self):
        """Adjust payment amount and use Odoo's standard writeoff mechanism."""
        if self.retention_enabled and self.retention_amount:
            total = sum(self.line_ids.mapped("amount_residual"))
            self.amount = total - self.retention_amount
            # Use Odoo's standard writeoff to handle the difference
            self.payment_difference_handling = "reconcile"
            if self.retention_account_id:
                self.writeoff_account_id = self.retention_account_id

    def _create_payment_vals_from_wizard(self, batch_result=None):
        """Pass adjusted amount to payment."""
        if batch_result is None:
            vals = super()._create_payment_vals_from_wizard()
        else:
            vals = super()._create_payment_vals_from_wizard(batch_result)
        if self.retention_enabled and self.retention_amount:
            vals["amount"] = self.amount
        return vals

    def _create_payments(self):
        """Create payment and create retention record."""
        # Recompute retention info from invoices
        self._compute_retention_info()

        # Set writeoff account before super call
        if self.retention_enabled and self.retention_amount:
            if not self.retention_account_id:
                raise UserError(_(
                    "Retention Receivable account is not configured. "
                    "Please set it in Accounting settings."
                ))
            if self.retention_account_id.account_type not in self._RETENTION_ALLOWED_ACCOUNT_TYPES:
                raise UserError(_(
                    "Retention account must be a Receivable or Current Asset account."
                ))
            self.payment_difference_handling = "reconcile"
            self.writeoff_account_id = self.retention_account_id

        payments = super()._create_payments()

        # Create retention receivable record after payment is reconciled
        if self.retention_enabled and self.retention_amount:
            invoice = self._get_invoice_from_lines()
            if not invoice:
                return payments

            payment = payments[0] if payments else self.env["account.payment"]

            # Find the writeoff line posted to the retention account
            writeoff_line = payment.line_ids.filtered(
                lambda l: l.account_id == self.retention_account_id
            )

            sale_order = invoice.invoice_line_ids.mapped("sale_line_ids.order_id")[:1] \
                if invoice.invoice_line_ids.mapped("sale_line_ids.order_id") else False

            retention_rec = self.env["sale.retention.receivable"].create({
                "partner_id": invoice.commercial_partner_id.id,
                "sale_order_id": sale_order.id if sale_order else False,
                "invoice_id": invoice.id,
                "payment_id": payment.id,
                "retention_percent": invoice.retention_percent,
                "retention_amount": self.retention_amount,
                "collected_amount": 0.0,
                "retention_account_id": self.retention_account_id.id,
                "invoice_date": invoice.invoice_date,
                "retention_due_date": invoice.retention_due_date,
                "state": "open",
            })

            if writeoff_line:
                writeoff_line.retention_receivable_id = retention_rec.id

        return payments
