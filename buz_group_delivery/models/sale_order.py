from odoo import models, fields, api


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    grouped_partner_ids = fields.Many2many(
        'res.partner',
        string='Grouped Partner Addresses',
        compute='_compute_grouped_partner_ids',
    )

    @api.depends('partner_id')
    def _compute_grouped_partner_ids(self):
        for order in self:
            if order.partner_id:
                order.grouped_partner_ids = self.env['res.partner'].search([
                    '|',
                    ('id', '=', order.partner_id.id),
                    ('parent_id', '=', order.partner_id.id),
                ])
            else:
                order.grouped_partner_ids = False

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        for order in self:
            if order.partner_id:
                # Auto set delivery address: prefer type 'delivery', then 'contact', then main partner
                delivery = self.env['res.partner'].search([
                    ('parent_id', '=', order.partner_id.id),
                    ('type', '=', 'delivery')
                ], limit=1)
                if not delivery:
                    delivery = self.env['res.partner'].search([
                        ('parent_id', '=', order.partner_id.id),
                        ('type', '=', 'contact')
                    ], limit=1)
                order.partner_shipping_id = delivery or order.partner_id
                # Auto set invoice address: prefer type 'invoice', then 'contact', then main partner
                invoice = self.env['res.partner'].search([
                    ('parent_id', '=', order.partner_id.id),
                    ('type', '=', 'invoice')
                ], limit=1)
                if not invoice:
                    invoice = self.env['res.partner'].search([
                        ('parent_id', '=', order.partner_id.id),
                        ('type', '=', 'contact')
                    ], limit=1)
                order.partner_invoice_id = invoice or order.partner_id
            else:
                order.partner_shipping_id = False
                order.partner_invoice_id = False


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    parent_partner_id = fields.Many2one(
        'res.partner',
        string='Commercial Partner',
        compute='_compute_parent_partner_id',
    )

    @api.depends('partner_id')
    def _compute_parent_partner_id(self):
        for picking in self:
            picking.parent_partner_id = (
                picking.partner_id.commercial_partner_id
                if picking.partner_id else False
            )
