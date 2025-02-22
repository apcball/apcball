from odoo import models, fields

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    x_studio_brand = fields.Char(string='Brand')
    x_studio_model = fields.Char(string='Model')