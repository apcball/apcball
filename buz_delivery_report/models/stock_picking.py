from odoo import models, fields, api

try:
    from bahttext import bahttext
except ImportError:
    bahttext = None


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

    def amount_to_text_th(self, amount):
        """Convert amount to Thai baht text"""
        if not bahttext:
            return ''
        try:
            return bahttext(abs(amount))
        except Exception:
            return ''

    def _get_move_chunks(self, chunk_size=7):
        """Split moves into chunks for report pagination"""
        self.ensure_one()
        moves = self.move_ids_without_package.sorted(key=lambda m: m.id)
        return [moves[i:i + chunk_size] for i in range(0, len(moves), chunk_size)]