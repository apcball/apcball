from odoo import models, fields, api, _

class AccountPayment(models.Model):
    _inherit = 'account.payment'

    def _post(self, soft=True):
        """Override to handle billing note payments"""
        res = super()._post(soft=soft)
        self._create_billing_note_payments()
        return res

    def _create_billing_note_payments(self):
        """Create payment records in billing notes"""
        for payment in self:
            # Skip if payment is not posted
            if payment.state != 'posted':
                continue

            # Find related billing notes through reconciled invoices
            reconciled_invoices = payment.reconciled_invoice_ids
            if not reconciled_invoices:
                continue

            billing_notes = self.env['billing.note'].search([
                ('invoice_ids', 'in', reconciled_invoices.ids),
                ('state', '=', 'confirm')
            ])

            for note in billing_notes:
                # Calculate amount for this billing note
                note_invoices = note.invoice_ids & reconciled_invoices
                note_total = sum(note_invoices.mapped('amount_total'))
                if not note_total:
                    continue

                # Calculate payment ratio and amount for this billing note
                total_payment = sum(note_invoices.mapped(lambda i: 
                    i.amount_total - i.amount_residual))
                payment_ratio = total_payment / note_total
                note_amount = payment.amount * payment_ratio

                if note_amount <= 0:
                    continue

                # Create payment record in billing note
                self.env['billing.note.payment'].create({
                    'billing_note_id': note.id,
                    'payment_id': payment.id,
                    'payment_date': payment.date,
                    'amount': note_amount,
                    'payment_method': self._get_billing_note_payment_method(),
                    'currency_id': payment.currency_id.id,
                    'company_id': payment.company_id.id,
                    'notes': f'Auto-created from payment {payment.name}'
                })

    def _get_billing_note_payment_method(self):
        """Map payment method to billing note payment method"""
        self.ensure_one()
        if self.journal_id.type == 'cash':
            return 'cash'
        elif self.journal_id.type == 'bank':
            return 'transfer'
        elif self.payment_method_line_id.code == 'check_printing':
            return 'check'
        return 'other'