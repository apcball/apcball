from odoo import models, fields



from odoo import models, fields, api

class HrExpenseSheet(models.Model):
    _inherit = "hr.expense.sheet"

    invoice_tax_ids = fields.Many2many(
        comodel_name="account.tax",
        string="Invoice Taxes",
        help="Taxes related to this expense sheet."
    )

    tax_invoice_ids = fields.One2many(
        comodel_name="account.move.tax.invoice",
        inverse_name="expense_sheet_id",
        string="Tax Invoices",
        help="Tax invoices related to this expense sheet.",
    )

    total_tax_base = fields.Monetary(
        string="Total Tax Base",
        compute="_compute_tax_totals",
        store=True,
    )
    total_tax_amount = fields.Monetary(
        string="Total Tax Amount", 
        compute="_compute_tax_totals",
        store=True,
    )

    @api.depends('tax_invoice_ids.tax_base_amount', 'tax_invoice_ids.balance')
    def _compute_tax_totals(self):
        """Compute total tax base and tax amount from tax invoices"""
        for sheet in self:
            sheet.total_tax_base = sum(sheet.tax_invoice_ids.mapped('tax_base_amount'))
            sheet.total_tax_amount = sum(sheet.tax_invoice_ids.mapped('balance'))

    def action_sheet_move_create(self):
        """Override to handle tax invoice validation"""
        # Skip tax invoice validation for expenses
        return super().action_sheet_move_create()
