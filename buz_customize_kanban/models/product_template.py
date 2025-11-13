from odoo import models, fields, api

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    price_with_vat = fields.Float(
        string='Price (Inc. VAT)',
        compute='_compute_price_with_vat',
        digits='Product Price'
    )
    
    available_qty = fields.Float(
        string='Available',
        compute='_compute_available_qty',
        digits='Product Unit of Measure'
    )

    @api.depends('list_price')
    def _compute_price_with_vat(self):
        for product in self:
            product.price_with_vat = product.list_price * 1.07
    
    @api.depends('qty_available', 'incoming_qty', 'outgoing_qty')
    def _compute_available_qty(self):
        for product in self:
            # Available = (On Hand + Incoming) - Outgoing
            product.available_qty = (product.qty_available + product.incoming_qty) - product.outgoing_qty