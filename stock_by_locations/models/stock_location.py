# Part of Odoo. See COPYRIGHT & LICENSE files for full copyright and licensing details.
from odoo import fields, models


class StockLocation(models.Model):
    _inherit = 'stock.location'

    exclude_from_product_cost = fields.Boolean(
        string='Exclude From Product Cost'
    )
    
    apply_in_sale = fields.Boolean(
        string='Apply in Sale Order',
    )
    
