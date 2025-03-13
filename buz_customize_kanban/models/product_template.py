from odoo import models, fields, api

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    price_with_vat = fields.Float(
        string='Price (Inc. VAT)',
        compute='_compute_price_with_vat',
        digits='Product Price'
    )

    @api.depends('list_price')
    def _compute_price_with_vat(self):
        for product in self:
            product.price_with_vat = product.list_price * 1.07