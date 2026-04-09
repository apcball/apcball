# -*- coding: utf-8 -*-
from odoo import fields, models

class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    external_ref = fields.Char(string='External Ref', index=True, copy=False)
    import_session_id = fields.Many2one('mrp.import.session', string='Import Session', copy=False)
    batch_id = fields.Char(string='Batch ID', copy=False)
