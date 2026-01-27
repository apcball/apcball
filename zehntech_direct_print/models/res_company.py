# -*- coding: utf-8 -*-
from odoo import fields, models
class ResCompany(models.Model):
    """Inheriting this class to add the Print-node credential need in config settings and use the multi company feature"""
    _inherit = 'res.company'

    api_key_print_node = fields.Char(string="API Key", help='API Key of the printNode')
    available_printers_id = fields.Many2one('printer.details', string='Available Printers',
                                            help='Available printers in the connected computer',
                                            config_parameter='zehntech_direct_print.available_printers_id')
    printers_ids = fields.Many2many('printer.details', string='Printers Details',
                                    help='Multiple Printers can connect and print.')
    multiple_printers = fields.Boolean(string='Multiple Printers', help='Enable if you have Multiple Printers',
                                       config_parameter='zehntech_direct_print.multiple_printers')
