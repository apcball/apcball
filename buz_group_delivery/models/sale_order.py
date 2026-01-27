from odoo import models, fields, api

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    grouped_partner_shipping_ids = fields.Many2many(
        'res.partner',
        string='Grouped Delivery Addresses',
        compute='_compute_grouped_partner_shipping_ids',
    )
    grouped_partner_invoice_ids = fields.Many2many(
        'res.partner',
        string='Grouped Invoice Addresses',
        compute='_compute_grouped_partner_invoice_ids',
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
    
    @api.depends('partner_id')
    def _compute_grouped_partner_invoice_ids(self):
        for order in self:
            if order.partner_id:
                # Get all child contacts with type 'invoice'
                invoice_addresses = self.env['res.partner'].search([
                    '|',
                    ('id', '=', order.partner_id.id),
                    '&',
                    ('parent_id', '=', order.partner_id.id),
                    ('type', '=', 'invoice'),
                ])
                order.grouped_partner_invoice_ids = invoice_addresses
            else:
                order.grouped_partner_invoice_ids = False

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        for order in self:
            if order.partner_id:
                # Auto set delivery address: first child of type 'delivery', else main partner
                delivery = self.env['res.partner'].search([
                    ('parent_id', '=', order.partner_id.id),
                    ('type', '=', 'delivery')
                ], limit=1)
                order.partner_shipping_id = delivery or order.partner_id
                # Auto set invoice address: first child of type 'invoice', else main partner
                invoice = self.env['res.partner'].search([
                    ('parent_id', '=', order.partner_id.id),
                    ('type', '=', 'invoice')
                ], limit=1)
                order.partner_invoice_id = invoice or order.partner_id
            else:
                order.partner_shipping_id = False
                order.partner_invoice_id = False