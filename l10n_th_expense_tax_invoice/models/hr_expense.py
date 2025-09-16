# Copyright 2024 Ecosoft Co., Ltd (http://ecosoft.co.th/)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)

from odoo import api, fields, models


class HrExpense(models.Model):
    _inherit = "hr.expense"

    tax_invoice_number = fields.Char(
        string="Tax Invoice Number",
        help="Tax invoice number from vendor for this expense line"
    )
    tax_invoice_date = fields.Date(
        string="Tax Invoice Date",
        help="Tax invoice date from vendor for this expense line"
    )

    @api.onchange('product_id')
    def _onchange_product_tax_invoice(self):
        """Clear tax invoice fields when product changes"""
        if self.product_id:
            self.tax_invoice_number = False
            self.tax_invoice_date = False


class HrExpenseSheet(models.Model):
    _inherit = "hr.expense.sheet"

    def _prepare_move_line_values(self):
        """Override to include tax invoice information in journal entries"""
        res = super()._prepare_move_line_values()
        
        # Add tax invoice information to account move lines
        for expense_line in self.expense_line_ids:
            if expense_line.tax_invoice_number and expense_line.tax_invoice_date:
                # Find the corresponding move line for this expense
                for move_line_vals in res:
                    if (move_line_vals.get('expense_id') == expense_line.id and 
                        move_line_vals.get('tax_ids')):
                        # Add tax invoice data to the move line
                        move_line_vals.update({
                            'tax_invoice_number': expense_line.tax_invoice_number,
                            'tax_invoice_date': expense_line.tax_invoice_date,
                        })
        
        return res