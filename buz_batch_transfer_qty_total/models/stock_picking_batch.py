# -*- coding: utf-8 -*-
from odoo import models, fields, api


class StockPickingBatch(models.Model):
    _inherit = 'stock.picking.batch'

    total_qty = fields.Float(
        string="Total Quantity",
        compute="_compute_total_qty",
        store=False,
        digits=(16, 4),
        help="Total quantity of all products in this batch transfer"
    )

    @api.depends('picking_ids.move_ids_without_package.quantity',
                 'picking_ids.move_ids_without_package.product_uom_qty',
                 'picking_ids.state')
    def _compute_total_qty(self):
        """
        Compute the total quantity for all transfers in this batch.
        Uses quantity if available, otherwise falls back to product_uom_qty.
        Excludes cancelled transfers.
        """
        for batch in self:
            total_quantity = 0.0
            for picking in batch.picking_ids:
                if picking.state != 'cancel':
                    for move in picking.move_ids_without_package:
                        # Use quantity if available, otherwise use product_uom_qty
                        quantity = move.quantity or move.product_uom_qty
                        total_quantity += quantity
            batch.total_qty = total_quantity