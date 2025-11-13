# Part of Odoo. See COPYRIGHT & LICENSE files for full copyright and licensing details.
from odoo import api, fields, models


class ProductCategory(models.Model):
    _inherit = 'product.category'

    property_cost_method = fields.Selection(selection_add=[('avco_by_location', 'AVCO by Location')],
                                            ondelete={'avco_by_location': 'cascade'})
