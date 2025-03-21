from odoo import models, fields

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # Physical Dimensions
    gross_width = fields.Float(string="Gross Width (cm)")
    gross_depth = fields.Float(string="Gross Depth (cm)")
    gross_height = fields.Float(string="Gross Height (cm)")
    cubic_meter = fields.Float(string="Cubic Meter")

    # Box Dimensions
    box_width = fields.Float(string="Box Width (cm)")
    box_depth = fields.Float(string="Box Depth (cm)")
    box_height = fields.Float(string="Box Height (cm)")
    
    # Add new Box Weight field
    box_weight = fields.Float(string="Box Weight (kg)", help="Weight of the product packaging")