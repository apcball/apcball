# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class TaxReportConfig(models.Model):
    _name = 'tax.report.config'
    _description = 'Tax Report Configuration'
    _order = 'sequence, name'

    name = fields.Char(string='Report Name', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(string='Active', default=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)
    tax_ids = fields.Many2many('account.tax', string='Taxes', help='Taxes to include in this report configuration')
    report_type = fields.Selection([
        ('sale', 'Sales Tax Report'),
        ('purchase', 'Purchase Tax Report'),
        ('both', 'Both Sales and Purchase')
    ], string='Report Type', default='both', required=True)
    description = fields.Text(string='Description')
    
    @api.model
    def get_default_config(self):
        """Get or create default tax report configuration"""
        config = self.search([('company_id', '=', self.env.company.id)], limit=1)
        if not config:
            config = self.create({
                'name': _('Default Tax Report'),
                'company_id': self.env.company.id,
                'report_type': 'both'
            })
        return config
    
    def action_generate_report(self):
        """Generate tax report using this configuration"""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Tax Report'),
            'res_model': 'tax.report.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_tax_config_id': self.id,
                'default_company_id': self.company_id.id,
                'default_tax_type': self.report_type if self.report_type != 'both' else 'all',
                'default_specific_tax_ids': [(6, 0, self.tax_ids.ids)] if self.tax_ids else False,
            }
        }
