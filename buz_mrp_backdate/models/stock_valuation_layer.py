# -*- coding: utf-8 -*-

from odoo import api, fields, models


class StockValuationLayer(models.Model):
    _inherit = 'stock.valuation.layer'

    backdate_remark = fields.Text(
        string='Backdate Remark',
        help='Remark from manufacturing order backdate',
        compute='_compute_backdate_remark',
        store=True,
    )

    @api.depends('stock_move_id.backdate_remark')
    def _compute_backdate_remark(self):
        """Compute backdate remark from related stock move"""
        for layer in self:
            layer.backdate_remark = layer.stock_move_id.backdate_remark or ''
