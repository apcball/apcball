# -*- coding: utf-8 -*-
from odoo import api, fields, models

class MrpImportLog(models.Model):
    _name = 'mrp.import.log'
    _description = 'MRP Import Log'
    _order = 'session_id, row_number'

    session_id = fields.Many2one('mrp.import.session', string='Session', ondelete='cascade', index=True)
    row_number = fields.Integer(string='Row Number')
    data_json = fields.Text(string='Raw Data (JSON)')
    state = fields.Selection([
        ('success', 'Success'),
        ('failed', 'Failed')
    ], string='Status', required=True)
    message = fields.Text(string='Message')
