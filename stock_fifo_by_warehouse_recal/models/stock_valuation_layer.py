# -*- coding: utf-8 -*-

from odoo import fields, models


class StockValuationLayer(models.Model):
    """Adds the flag that exempts a layer from FIFO repair."""
    _inherit = 'stock.valuation.layer'

    locked = fields.Boolean(
        string='Locked',
        default=False,
        index=True,
        help='Exempt this layer from the FIFO repair wizard. Set it on layers '
             'whose remaining quantity and value were decided by hand and must '
             'stay as they are. A product/warehouse pair holding any locked '
             'layer is skipped entirely — repairing part of a FIFO queue would '
             'leave the rest inconsistent with it.'
    )
