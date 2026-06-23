# -*- coding: utf-8 -*-

from odoo import models, fields, api


class MarketplaceStockHistory(models.Model):
    _name = 'buz.marketplace.stock.history'
    _description = 'Marketplace Stock History'
    _order = 'create_date desc'

    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        index=True
    )
    account_id = fields.Many2one(
        'buz.marketplace.account',
        string='Marketplace Account',
        required=True,
        index=True
    )
    change_type = fields.Selection([
        ('fetch', 'Fetch from Marketplace'),
        ('refill', 'Refill Buffer Stock'),
        ('push', 'Push to Marketplace'),
        ('transfer_to_buffer', 'Transfer to Buffer'),
        ('order_fulfillment', 'Order Fulfillment'),
    ], string='Change Type', required=True, index=True)
    old_qty = fields.Float(
        string='Old Quantity',
        digits='Product Unit of Measure'
    )
    new_qty = fields.Float(
        string='New Quantity',
        digits='Product Unit of Measure'
    )
    marketplace_qty = fields.Float(
        string='Marketplace Quantity',
        digits='Product Unit of Measure'
    )
    difference = fields.Float(
        string='Difference',
        compute='_compute_difference',
        store=True,
        digits='Product Unit of Measure'
    )
    stock_move_id = fields.Many2one(
        'stock.move',
        string='Stock Move',
        ondelete='set null'
    )
    user_id = fields.Many2one(
        'res.users',
        string='User',
        default=lambda self: self.env.user,
        required=True
    )
    notes = fields.Text(
        string='Notes'
    )
    company_id = fields.Many2one(
        'res.company',
        related='account_id.company_id',
        store=True,
        index=True
    )

    @api.depends('old_qty', 'new_qty')
    def _compute_difference(self):
        for record in self:
            record.difference = record.new_qty - record.old_qty
