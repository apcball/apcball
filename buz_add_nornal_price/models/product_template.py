# -*- coding: utf-8 -*-
from odoo import models, fields

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    normal_price = fields.Float(string='Normal Price', help='Normal Price')
