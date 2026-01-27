from odoo import models, fields, api


class ResPartner(models.Model):
    _inherit = 'res.partner'

    warranty_card_count = fields.Integer(
        string='Warranty Cards',
        compute='_compute_warranty_card_count',
        help='Number of warranty cards for this partner'
    )

    @api.depends()
    def _compute_warranty_card_count(self):
        """Compute the number of warranty cards for this partner"""
        for partner in self:
            partner.warranty_card_count = self.env['warranty.card'].search_count([
                ('partner_id', '=', partner.id)
            ])

    def action_view_warranty_cards(self):
        """Action to view warranty cards for this partner"""
        self.ensure_one()
        action = self.env.ref('buz_warranty_management.action_warranty_card').read()[0]
        action['domain'] = [('partner_id', '=', self.id)]
        action['context'] = {
            'default_partner_id': self.id,
            'form_view_initial_mode': 'edit'
        }
        return action