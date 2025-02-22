from odoo import models, fields

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    name_eng = fields.Char(string='Product Name (English)', help='Product name in English')