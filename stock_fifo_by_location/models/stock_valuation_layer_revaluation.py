# -*- coding: utf-8 -*-
"""Inventory Revaluation wizard: keep origin_remaining_value in step.

Standard (stock_account) spreads ``added_value`` over every layer of the product that still
has remaining_qty and adds each share to that layer's ``remaining_value`` only. The cost
origin keeps the old ``origin_remaining_value``, and calculate_fifo_cost prices later issues
at origin_remaining_value / origin_remaining_qty, so the next issue ignores the revaluation.
"""

from odoo import models


class StockValuationLayerRevaluation(models.TransientModel):
    _inherit = 'stock.valuation.layer.revaluation'

    def action_validate_revaluation(self):
        self.ensure_one()
        layer_model = self.env['stock.valuation.layer']
        in_stock = layer_model.search([
            ('product_id', '=', self.product_id.id),
            ('remaining_qty', '>', 0),
            ('company_id', '=', self.company_id.id),
        ])
        before = {layer.id: layer.remaining_value for layer in in_stock}

        res = super().action_validate_revaluation()

        # what standard added to each layer's remaining_value goes to its cost origin too
        in_stock.invalidate_recordset(['remaining_value'])
        for layer in in_stock:
            delta = layer.remaining_value - before[layer.id]
            if not delta:
                continue
            origin = layer.origin_valuation_layer_id or layer
            if origin.origin_remaining_qty <= 0:
                continue
            origin.sudo().origin_remaining_value += delta
        return res
