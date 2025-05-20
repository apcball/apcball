from odoo import models, fields, api

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    grouped_partner_shipping_ids = fields.Many2many(
        'res.partner',
        string='Grouped Delivery Addresses',
        compute='_compute_grouped_partner_shipping_ids',
    )

    @api.depends('partner_id')
    def _compute_grouped_partner_shipping_ids(self):
        for order in self:
            if order.partner_id:
                # Get all child contacts with type 'delivery'
                delivery_addresses = self.env['res.partner'].search([
                    '|',
                    ('id', '=', order.partner_id.id),
                    '&',
                    ('parent_id', '=', order.partner_id.id),
                    ('type', '=', 'delivery'),
                ])
                order.grouped_partner_shipping_ids = delivery_addresses
            else:
                order.grouped_partner_shipping_ids = False

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        # Set partner_shipping_id to partner_id when partner changes
        if self.partner_id:
            self.partner_shipping_id = self.partner_id