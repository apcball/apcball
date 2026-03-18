# -*- coding: utf-8 -*-
from odoo import models, fields, api

class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    # No specific override needed currently if created via stock.rule
    # But this file is included for potential future extensions as requested.
    pass
