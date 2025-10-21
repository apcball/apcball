# Part of buz_warranty_rma_management Odoo module.
# See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api


class RepairOrderInherit(models.Model):
    _inherit = 'repair.order'

    buz_claim_id = fields.Many2one(
        'buz.warranty.claim',
        string='Warranty Claim',
        copy=False
    )

    @api.onchange('buz_claim_id')
    def _onchange_claim_id(self):
        """Auto-fill product, lot, and partner from claim"""
        if self.buz_claim_id:
            self.product_id = self.buz_claim_id.product_id
            self.lot_id = self.buz_claim_id.lot_id
            self.partner_id = self.buz_claim_id.partner_id

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