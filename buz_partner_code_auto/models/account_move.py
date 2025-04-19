from odoo import models, fields, api

class AccountMove(models.Model):
    _inherit = 'account.move'

    partner_code = fields.Char(
        string='Partner Code',
        help='Enter partner code to auto-fill partner details'
    )

    @api.onchange('partner_code')
    def _onchange_partner_code(self):
        if self.partner_code:
            # Convert to uppercase for case-insensitive search
            partner_code = self.partner_code.strip().upper()
            domain = [('partner_code', '=ilike', partner_code)]
            
            # Add appropriate domain based on move type
            if self.move_type in ('out_invoice', 'out_refund', 'out_receipt'):
                domain.append(('customer_rank', '>', 0))
            elif self.move_type in ('in_invoice', 'in_refund', 'in_receipt'):
                domain.append(('supplier_rank', '>', 0))
            
            partner = self.env['res.partner'].search(domain, limit=1)
            if partner:
                self.partner_id = partner.id
            else:
                message = 'No customer found with this partner code.' if self.move_type in ('out_invoice', 'out_refund', 'out_receipt') else 'No vendor found with this partner code.'
                return {
                    'warning': {
                        'title': 'Warning',
                        'message': message
                    }
                }

    @api.onchange('partner_id')
    def _onchange_partner_id_code(self):
        if self.partner_id and self.partner_id.partner_code:
            self.partner_code = self.partner_id.partner_code