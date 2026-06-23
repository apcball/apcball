# -*- coding: utf-8 -*-

from odoo import models, fields


class MarketplaceOrderLine(models.Model):
    _name = 'buz.marketplace.order.line'
    _description = 'Marketplace Order Line'

    order_id = fields.Many2one(
        'buz.marketplace.order',
        string='Order',
        required=True,
        ondelete='cascade',
        index=True
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True
    )
    marketplace_product_id = fields.Many2one(
        'buz.marketplace.product',
        string='Marketplace Product'
    )
    product_name = fields.Char(
        string='Product Name'
    )
    quantity = fields.Float(
        string='Quantity',
        digits='Product Unit of Measure',
        default=1.0
    )
    price_unit = fields.Float(
        string='Unit Price',
        digits='Product Price'
    )
    sale_order_line_id = fields.Many2one(
        'sale.order.line',
        string='Sale Order Line'
    )
    company_id = fields.Many2one(
        'res.company',
        related='order_id.company_id',
        store=True
    )
