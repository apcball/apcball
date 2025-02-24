from odoo import models, fields, api

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    delivery_note = fields.Text(string='Delivery Note')
    customer_reference = fields.Char(string='Customer Reference')
    delivery_instructions = fields.Text(string='Delivery Instructions')

    def get_delivery_summary(self):
        """Get delivery summary for report"""
        self.ensure_one()
        total_quantity = sum(
            sum(ml.quantity for ml in move.move_line_ids)
            for move in self.move_ids_without_package
        )
        return {
            'total_packages': len(self.move_line_ids_without_package),
            'total_quantity': total_quantity,
            'carrier_name': self.carrier_id.name if self.carrier_id else '',
        }