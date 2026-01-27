from odoo import models, fields

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    sku = fields.Char(string='SKU', help='Stock Keeping Unit')
