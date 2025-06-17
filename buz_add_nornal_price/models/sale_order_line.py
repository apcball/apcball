# -*- coding: utf-8 -*-
from odoo import models, fields, api

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    normal_price = fields.Float(string='Normal Price', related='product_id.normal_price', store=True, readonly=True)
