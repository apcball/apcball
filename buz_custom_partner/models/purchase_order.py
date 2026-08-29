# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    partner_code = fields.Char(
        string='Vendor Code',
        help="Enter a vendor code to select the vendor automatically.",
    )

    @api.onchange('partner_code')
    def _onchange_partner_code(self):
        if not self.partner_code:
            return

        domain = [
            ('partner_code', '=ilike', self.partner_code.strip()),
            ('supplier_rank', '>', 0),
        ]
        if self.company_id:
            domain += [
                '|', ('company_id', '=', False),
                ('company_id', '=', self.company_id.id),
            ]
        partner = self.env['res.partner'].search(domain, limit=1)
        if partner:
            self.partner_id = partner
            return
        return {
            'warning': {
                'title': _('Warning'),
                'message': _('No vendor found with this partner code.'),
            },
        }

    @api.onchange('partner_id')
    def _onchange_partner_id_code(self):
        if self.partner_id.partner_code:
            self.partner_code = self.partner_id.partner_code
