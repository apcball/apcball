# -*- coding: utf-8 -*-

from odoo import api, fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    backdate_remark = fields.Text(
        string='Backdate Remark',
        help='Remark from manufacturing order backdate',
        compute='_compute_backdate_remark',
        store=True,
    )

    @api.depends('production_id.backdate_remark', 'raw_material_production_id.backdate_remark')
    def _compute_backdate_remark(self):
        """Compute backdate remark from related MO"""
        for move in self:
            remark = ''
            if move.production_id:
                remark = move.production_id.backdate_remark or ''
            elif move.raw_material_production_id:
                remark = move.raw_material_production_id.backdate_remark or ''
            move.backdate_remark = remark
