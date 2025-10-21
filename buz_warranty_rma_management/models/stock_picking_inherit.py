# Part of buz_warranty_rma_management Odoo module.
# See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api


class StockPickingInherit(models.Model):
    _inherit = 'stock.picking'

    buz_claim_id = fields.Many2one(
        'buz.warranty.claim',
        string='Warranty Claim',
        copy=False
    )

    def action_view_warranty_claim(self):
        """Action to view the related warranty claim"""
        self.ensure_one()
        if self.buz_claim_id:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Warranty Claim'),
                'res_model': 'buz.warranty.claim',
                'res_id': self.buz_claim_id.id,
                'view_mode': 'form',
                'target': 'current',
            }
        return False