from odoo import models, fields, api

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def get_delivery_report_values(self):
        """
        Get additional values for the delivery report
        """
        self.ensure_one()
        return {
            'total_weight': sum(move.product_id.weight * move.product_uom_qty for move in self.move_ids),
            'total_volume': sum(move.product_id.volume * move.product_uom_qty for move in self.move_ids),
            'total_packages': len(self.package_ids),
        }