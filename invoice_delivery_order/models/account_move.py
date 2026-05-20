# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    picking_ids = fields.Many2many(
        'stock.picking', 'account_move_stock_picking_rel',
        'account_move_id', 'stock_picking_id',
        string='Delivery Orders',
        domain="[('id', 'in', available_picking_ids)]",
        help='Select related Delivery Orders to display on the invoice document.',
    )
    available_picking_ids = fields.Many2many(
        'stock.picking', compute='_compute_available_picking_ids',
        string='Available DOs',
    )

    @api.depends('line_ids.sale_line_ids', 'partner_id')
    def _compute_available_picking_ids(self):
        Picking = self.env['stock.picking']
        for move in self:
            pickings = Picking.browse()
            # From SO linked via invoice lines → sale.line → sale.order → pickings
            sale_orders = move.line_ids.sale_line_ids.order_id
            if sale_orders:
                pickings |= sale_orders.mapped('picking_ids').filtered(
                    lambda p: p.picking_type_id.code == 'outgoing' and p.state == 'done'
                )
            # Fallback: all done outgoing pickings of the partner
            if not pickings and move.partner_id:
                pickings = Picking.search([
                    ('partner_id', '=', move.partner_id.commercial_partner_id.id),
                    ('picking_type_id.code', '=', 'outgoing'),
                    ('state', '=', 'done'),
                ])
            move.available_picking_ids = pickings
