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

    @api.depends('move_ids.state', 'move_ids.quantity', 'move_ids.product_uom')
    def _compute_reserve_qty(self):
        for line in self:
            reserved = 0.0
            for move in line.move_ids.filtered(
                lambda m: m.state in ('assigned', 'partially_available')
            ):
                reserved += move.product_uom._compute_quantity(
                    move.quantity, line.product_uom
                )
            line.reserve_qty = reserved
