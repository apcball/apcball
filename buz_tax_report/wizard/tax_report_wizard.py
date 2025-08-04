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
    tax_config_id = fields.Many2one('tax.report.config', string='Tax Report Configuration', help="Select a predefined tax report configuration")
    
    @api.onchange('tax_config_id')
    def _onchange_tax_config_id(self):
        """Update fields when tax config is selected"""
        if self.tax_config_id:
            config = self.tax_config_id
            self.tax_type = config.report_type if config.report_type != 'both' else 'all'
            if config.tax_ids:
                self.specific_tax_ids = [(6, 0, config.tax_ids.ids)]
    
    @api.model
    def default_get(self, fields_list):
        """Set default values"""
        res = super().default_get(fields_list)
        if 'date_from' in fields_list and not res.get('date_from'):
            # Default to first day of current month
            today = fields.Date.today()
            res['date_from'] = today.replace(day=1)
        if 'date_to' in fields_list and not res.get('date_to'):
            # Default to today
            res['date_to'] = fields.Date.today()
        return res
    
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
    
    def action_save_as_config(self):
        """Save current settings as a new tax report configuration"""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Save as Tax Report Configuration'),
            'res_model': 'tax.report.config',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_name': f"Tax Report - {fields.Date.today().strftime('%B %Y')}",
                'default_company_id': self.company_id.id,
                'default_report_type': self.tax_type if self.tax_type != 'all' else 'both',
                'default_tax_ids': [(6, 0, self.specific_tax_ids.ids)] if self.specific_tax_ids else False,
                'default_description': f"Generated from wizard on {fields.Datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            }
        }
