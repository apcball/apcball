# Part of Odoo. See COPYRIGHT & LICENSE files for full copyright and licensing details.
from odoo import fields, models, _


class ProductCostLocationHistory(models.Model):
    _name = 'product.cost.location.history'
    _description = 'Product Average History Log'
    _order = 'date'

    name = fields.Char()
    product_id = fields.Many2one(
        comodel_name='product.product',
        ondelete='restrict',
        index=True
    )
    product_tmp_id = fields.Many2one(
        comodel_name='product.template',
        related='product_id.product_tmpl_id',
        store=True,
        ondelete='restrict',
    )
    move_id = fields.Many2one(
        comodel_name='stock.move',
        ondelete='restrict',
    )
    qty = fields.Float()
    standard_price = fields.Float(
        string='Cost',
        digits='Product Price',
    )
    location_id = fields.Many2one(
        comodel_name='stock.location',
        index=True,
        ondelete='restrict',
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        default=lambda self: self.env.company,
    )
    date = fields.Datetime()
    former_qty = fields.Float()
    former_avg = fields.Float()
    incoming_qty = fields.Float()
    incoming_cost = fields.Float()
    exclude_from_product_cost = fields.Boolean()
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        ondelete='restrict',
    )
    is_old_calculation = fields.Boolean()
