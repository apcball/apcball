# -*- coding: utf-8 -*-
#############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2024-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Gokul PI (<https://www.cybrosys.com>)
#
#    You can modify it under the terms of the GNU LESSER
#    GENERAL PUBLIC LICENSE (LGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU LESSER GENERAL PUBLIC LICENSE (LGPL v3) for more details.
#
#    You should have received a copy of the GNU LESSER GENERAL PUBLIC LICENSE
#    (LGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
#############################################################################
from odoo import models, fields, api


class SaleOrderLine(models.Model):
    """Inheriting sale order line for adding some fields"""
    _inherit = 'sale.order.line'

    order_line_image = fields.Binary(string="Image",
                                     related="product_id.image_1920",
                                     help='Corresponding image of product')
    contact_email = fields.Char(related="order_partner_id.email",
                                string='Email',
                                help='Email of the customer')
    contact_phone = fields.Char(related="order_partner_id.phone",
                                string='Phone',
                                help='Phone number of the customer')
    reserve_qty = fields.Float(
        string="Reserve Qty",
        compute='_compute_reserve_qty',
        help='Quantity reserved in stock for this line',
    )

    project_name = fields.Char(
        related="order_id.project_name",
        string="Project Name",
    )
    partner_shipping_id = fields.Many2one(
        related="order_id.partner_shipping_id",
        string="Delivery Address",
    )
    team_id = fields.Many2one(
        related="order_id.team_id",
        string="Sales Team",
        store=True,
        readonly=True,
    )
    sku = fields.Char(
        string="SKU",
        related="product_id.sku",
        help='Stock Keeping Unit',
    )

    create_date_only = fields.Date(
        string="Create Date",
        compute='_compute_create_date_only',
        store=True,
    )

    forecast_expected_date_only = fields.Date(
        string="Forecast Expected Date",
        compute='_compute_forecast_expected_date_only',
        store=True,
    )

    date_done = fields.Date(
        string="Delivery Date",
        compute='_compute_date_done',
        store=True,
    )

    is_pending_delivery = fields.Boolean(
        string="Pending Delivery",
        compute='_compute_is_pending_delivery',
        store=True,
    )

    pending_amount = fields.Monetary(
        string="Pending Amount",
        currency_field="currency_id",
        compute='_compute_pending_amount',
        store=True,
        help='Sales amount for the quantity that is still waiting to be delivered.',
    )

    picking_scheduled_date = fields.Date(
        string="Scheduled Date",
        compute='_compute_picking_scheduled_date',
        store=True,
    )

    qty_to_deliver_stored = fields.Float(
        string="Pending Qty",
        compute='_compute_qty_to_deliver_stored',
        store=True,
        help='Quantity that is still pending to be delivered',
    )

    @api.depends('create_date')
    def _compute_create_date_only(self):
        for line in self:
            line.create_date_only = line.create_date.date() if line.create_date else False

    @api.depends('forecast_expected_date')
    def _compute_forecast_expected_date_only(self):
        for line in self:
            line.forecast_expected_date_only = line.forecast_expected_date.date() if line.forecast_expected_date else False

    @api.depends('move_ids.picking_id.date_done')
    def _compute_date_done(self):
        for line in self:
            dates = line.move_ids.picking_id.mapped('date_done')
            dates = [d for d in dates if d]
            line.date_done = max(dates).date() if dates else False

    @api.depends('move_ids.picking_id.scheduled_date')
    def _compute_picking_scheduled_date(self):
        for line in self:
            dates = line.move_ids.picking_id.mapped('scheduled_date')
            dates = [d for d in dates if d]
            line.picking_scheduled_date = max(dates).date() if dates else False

    @api.depends('move_ids.state', 'move_ids.quantity', 'move_ids.product_uom',
                 'move_ids.location_dest_id')
    def _compute_reserve_qty(self):
        for line in self:
            reserved = 0.0
            for move in line.move_ids.filtered(
                lambda m: m.state in ('assigned', 'partially_available')
                and m.location_dest_id.usage == 'customer'
                and (not m.origin_returned_move_id or m.to_refund)
            ):
                reserved += move.product_uom._compute_quantity(
                    move.quantity, line.product_uom
                )
            line.reserve_qty = reserved

    @api.depends('state', 'product_uom_qty', 'qty_delivered')
    def _compute_is_pending_delivery(self):
        for line in self:
            line.is_pending_delivery = (
                line.state == 'sale'
                and line.product_uom_qty > line.qty_delivered
            )

    @api.depends('qty_to_deliver')
    def _compute_qty_to_deliver_stored(self):
        for line in self:
            line.qty_to_deliver_stored = line.qty_to_deliver

    @api.depends('qty_to_deliver', 'product_uom_qty', 'price_subtotal')
    def _compute_pending_amount(self):
        for line in self:
            ordered_qty = line.product_uom_qty or 0.0
            pending_qty = max(line.qty_to_deliver or 0.0, 0.0)
            if ordered_qty:
                line.pending_amount = line.price_subtotal * pending_qty / ordered_qty
            else:
                line.pending_amount = 0.0
