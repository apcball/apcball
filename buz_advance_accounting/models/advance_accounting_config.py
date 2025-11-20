# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class AdvanceAccountingConfig(models.Model):
    _name = 'advance.accounting.config'
    _description = 'Advance Accounting Configuration'
    _rec_name = 'company_id'
    
    company_id = fields.Many2one(
        'res.company', 
        string='Company', 
        required=True, 
        default=lambda self: self.env.company,
        index=True
    )
    exchange_rate_diff_account_id = fields.Many2one(
        'account.account', 
        string='Exchange Rate Difference Account',
        domain="[('deprecated', '=', False), ('company_id', '=', company_id)]",
        help='Account used for recording exchange rate differences'
    )
    
    _sql_constraints = [
        ('company_unique', 'unique(company_id)', 'Only one configuration per company is allowed!')
    ]
    
    @api.model
    def get_config(self):
        """Get the configuration for the current company"""
        company = self.env.company
        config = self.search([('company_id', '=', company.id)], limit=1)
        if not config:
            # Create default configuration if not exists
            config = self.create({'company_id': company.id})
        return config
    
    def get_exchange_rate_diff_account(self):
        """Get the exchange rate difference account for the current company"""
        config = self.get_config()
        return config.exchange_rate_diff_account_id