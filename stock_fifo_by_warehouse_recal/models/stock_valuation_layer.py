# -*- coding: utf-8 -*-

from odoo import fields, models


class StockValuationLayer(models.Model):
    """
    Inherit stock.valuation.layer to add locked field for recalculation control.
    """
    _inherit = 'stock.valuation.layer'

    locked = fields.Boolean(
        string='Locked',
        default=False,
        index=True,
        help='If checked, this layer will not be recalculated again by FIFO recalculation tools.'
    )
