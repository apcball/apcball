from odoo import models, fields, api
from num2words import num2words
import base64
import os

class AccountPayment(models.Model):
    _inherit = 'account.payment'

    def _get_invoice_payment_amount(self, invoice):
        """Get the amount paid for a specific invoice by this payment."""
        self.ensure_one()
        payment_lines = invoice.line_ids.filtered(
            lambda line: line.account_type in ('asset_receivable', 'liability_payable')
        )
        matching_lines = payment_lines.mapped('matched_debit_ids') + payment_lines.mapped('matched_credit_ids')
        matching_payments = matching_lines.mapped('debit_move_id.payment_id') + matching_lines.mapped('credit_move_id.payment_id')
        
        if self in matching_payments:
            amount = 0
            for line in matching_lines:
                if line.debit_move_id.payment_id == self or line.credit_move_id.payment_id == self:
                    amount += line.amount
            return amount
        return 0.0

    def get_report_background(self):
        # Get the module path
        module_path = os.path.dirname(os.path.dirname(__file__))
        image_path = os.path.join(module_path, 'static', 'img', 'receipt.pdf')
        
        try:
            with open(image_path, 'rb') as f:
                return base64.b64encode(f.read()).decode()
        except Exception as e:
            return False