# -*- coding: utf-8 -*-
from odoo import models, fields, api


class EpsonConfig(models.Model):
    _name = 'buz.epson.config'
    _description = 'Epson Print Configuration'
    _order = 'name'

    name = fields.Char(string='Configuration Name', required=True)
    agent_url = fields.Char(string='Agent URL', required=True, 
                           help="URL of the Local Print Agent, e.g., http://192.168.1.55:5000/print")
    default_printer = fields.Char(string='Default Printer', required=True,
                                 help="Printer name as configured in the system, e.g., Epson_LQ310")
    active = fields.Boolean(string='Active', default=True)
    
    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'Configuration name must be unique!'),
    ]
    
    @api.model
    def get_active_config(self):
        """Get the active configuration"""
        return self.search([('active', '=', True)], limit=1)