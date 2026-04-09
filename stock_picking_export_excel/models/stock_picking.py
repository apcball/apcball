from odoo import models

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def action_export_excel(self):
        # We need to make sure we don't open wizard if only 1 record is selected
        if len(self) == 1:
            return {
                'type': 'ir.actions.act_url',
                'url': f'/stock_picking_export/{self.id}',
                'target': 'self',
            }
        else:
            return {
                'name': 'Export Stock Picking',
                'type': 'ir.actions.act_window',
                'res_model': 'stock.picking.export.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {'default_picking_ids': self.ids},
            }
