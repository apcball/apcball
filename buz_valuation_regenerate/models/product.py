from odoo import models


class ProductProduct(models.Model):
    _inherit = 'product.product'
    
    def action_open_valuation_regenerate_wizard(self):
        """Open the valuation regeneration wizard"""
        self.ensure_one()
        return {
            'name': 'Re-Generate Valuation Layers',
            'type': 'ir.actions.act_window',
            'res_model': 'valuation.regenerate.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_product_ids': self.ids,
                'default_company_id': self.company_id.id,
                'default_mode': 'product',
            }
        }