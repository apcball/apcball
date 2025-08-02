# -*- coding: utf-8 -*-
from odoo import fields, models, api, _
from odoo.exceptions import UserError

class TaxReportWizard(models.TransientModel):
    _name = 'tax.report.wizard'
    _description = 'Tax Report Wizard'

    date_from = fields.Date(string='Start Date', required=True)
    date_to = fields.Date(string='End Date', required=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)
    display_details = fields.Boolean(string='Display Details', default=False, help="Show detailed journal items")
    tax_type = fields.Selection([
        ('all', 'All Taxes'),
        ('sale', 'Sales Taxes'),
        ('purchase', 'Purchase Taxes')
    ], string='Tax Type', default='all', required=True)
    specific_tax_ids = fields.Many2many('account.tax', string='Specific Taxes', help="Select specific taxes to include (optional)")
    
    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for record in self:
            if record.date_from and record.date_to and record.date_from > record.date_to:
                raise UserError(_('Start Date cannot be greater than End Date.'))

    def action_generate_xlsx(self):
        if not self.date_from or not self.date_to:
            raise UserError(_('Please select both Start Date and End Date.'))
            
        return {
            'type': 'ir.actions.report',
            'report_name': 'buz_tax_report.tax_report_xlsx',
            'report_type': 'xlsx',
            'data': {'form': self.read()[0]},
            'context': self.env.context,
        }
