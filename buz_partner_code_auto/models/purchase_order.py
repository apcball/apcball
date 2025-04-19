from odoo import models, fields, api

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    partner_code = fields.Char(
        string='Partner Code',
        help='Enter partner code to auto-fill vendor details'
    )

    @api.onchange('partner_code')
    def _onchange_partner_code(self):
        if self.partner_code:
            # Convert to uppercase for case-insensitive search
            partner_code = self.partner_code.strip().upper()
            partner = self.env['res.partner'].search([
                ('partner_code', '=ilike', partner_code),
                ('supplier_rank', '>', 0)
            ], limit=1)
            if partner:
                self.partner_id = partner.id
            else:
                return {
                    'warning': {
                        'title': 'Warning',
                        'message': 'No vendor found with this partner code.'
                    }
                }

    @api.onchange('partner_id')
    def _onchange_partner_id_code(self):
        if self.partner_id and self.partner_id.partner_code:
            self.partner_code = self.partner_id.partner_code