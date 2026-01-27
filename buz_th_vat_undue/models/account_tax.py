from odoo import models, fields, api

class AccountTax(models.Model):
    _inherit = 'account.tax'

    is_vat_undue = fields.Boolean(string="Is VAT Undue", help="Check this if this tax represents a VAT Undue (deferred input tax).")
    undue_conversion_tax_id = fields.Many2one('account.tax', string="Target VAT Tax", help="Tax to use when converting Undue to Input (for Tags).")
    undue_input_vat_account_id = fields.Many2one('account.account', string="Input VAT Account", help="Account to use when converting Undue VAT to Input VAT. This is typically the Input VAT account (e.g., 116600).")

    @api.onchange('undue_conversion_tax_id')
    def _onchange_undue_conversion_tax_id(self):
        """Auto-fill Input VAT Account from target tax repartition"""
        if self.undue_conversion_tax_id and not self.undue_input_vat_account_id:
            rep_line = next((l for l in self.undue_conversion_tax_id.invoice_repartition_line_ids 
                           if l.repartition_type == 'tax' and l.account_id), None)
            if rep_line:
                self.undue_input_vat_account_id = rep_line.account_id

