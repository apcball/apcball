# Part of Odoo. See COPYRIGHT & LICENSE files for full copyright and licensing details.
from odoo import fields, models, _


class ProductCostLocation(models.TransientModel):
    _name = 'product.cost.location'
    _description = 'Product Cost Location'

    product_id = fields.Many2one('product.product', string='Product')
    qty = fields.Float()
    standard_price = fields.Float('Cost', digits='Product Price')
    location_id = fields.Many2one('stock.location', string='Location')
    company_id = fields.Many2one('res.company', string='Company')
    exclude_from_product_cost = fields.Boolean()
