# -*- coding: utf-8 -*-
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_ai_bot = fields.Boolean(string='AI Bot', default=False, index=True)
