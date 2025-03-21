from odoo import models, fields, api

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # Physical Dimensions
    gross_width = fields.Float(string="Gross Width (cm)")
    gross_depth = fields.Float(string="Gross Depth (cm)")
    gross_height = fields.Float(string="Gross Height (cm)")
    cubic_meter = fields.Float(string="Cubic Meter (m³)", compute='_compute_cubic_meter', store=True)

    @api.depends('gross_width', 'gross_depth', 'gross_height')
    def _compute_cubic_meter(self):
        for record in self:
            # Convert cm³ to m³ by dividing by 1,000,000 (100*100*100)
            record.cubic_meter = (record.gross_width * record.gross_depth * record.gross_height) / 1000000.0

    # Box Dimensions
    box_width = fields.Float(string="Box Width (cm)")
    box_depth = fields.Float(string="Box Depth (cm)")
    box_height = fields.Float(string="Box Height (cm)")
    
    # Add new Box Weight field
    box_weight = fields.Float(string="Box Weight (kg)", help="Weight of the product packaging")