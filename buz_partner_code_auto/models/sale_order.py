from odoo import models, fields, api

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    partner_code = fields.Char(
        string='Partner Code',
        help='Enter partner code to auto-fill customer details'
    )

    @api.onchange('partner_code')
    def _onchange_partner_code(self):
        if self.partner_code:
            # Convert to uppercase for case-insensitive search
            partner_code = self.partner_code.strip().upper()
            partner = self.env['res.partner'].search([
                ('partner_code', '=ilike', partner_code),
                ('customer_rank', '>', 0)
            ], limit=1)
            if partner:
                self.partner_id = partner.id
            else:
                return {
                    'warning': {
                        'title': 'Warning',
                        'message': 'No customer found with this partner code.'
                    }
                }