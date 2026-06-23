# -*- coding: utf-8 -*-

from odoo import models, fields


class ProductProduct(models.Model):
    _inherit = 'product.product'

    marketplace_sku = fields.Char(
        string='Marketplace SKU',
        help='SKU used on marketplace platforms (Shopee, Lazada)'
    )
    marketplace_product_ids = fields.One2many(
        'buz.marketplace.product',
        'product_id',
        string='Marketplace Products'
    )
