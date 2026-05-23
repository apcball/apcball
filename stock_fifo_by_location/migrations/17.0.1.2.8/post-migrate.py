# -*- coding: utf-8 -*-
"""
Migration for v17.0.1.2.8

Backfills cost-origin and warehouse-position fields introduced by the
Transfer != Consumption design.
"""

import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _logger.info("=" * 80)
    _logger.info("Starting migration to v17.0.1.2.8 - Cost Origin / Position Backfill")
    _logger.info("=" * 80)

    _ensure_indexes(cr)
    self_origin_count = _backfill_self_origin_layers(env)
    transfer_origin_count, unresolved_count = _backfill_transfer_position_layers(env)

    _logger.info("✅ Self-origin layers backfilled: %s", self_origin_count)
    _logger.info("✅ Transfer position layers backfilled: %s", transfer_origin_count)
    _logger.info("⚠️ Transfer layers unresolved for manual review: %s", unresolved_count)
    _logger.info("=" * 80)
    _logger.info("Migration to v17.0.1.2.8 completed")
    _logger.info("=" * 80)


def _ensure_indexes(cr):
    cr.execute("""
        CREATE INDEX IF NOT EXISTS stock_valuation_layer_origin_idx
        ON stock_valuation_layer (origin_valuation_layer_id, warehouse_id, product_id)
    """)
    cr.execute("""
        CREATE INDEX IF NOT EXISTS stock_valuation_layer_transfer_move_idx
        ON stock_valuation_layer (transfer_move_id)
    """)


def _backfill_self_origin_layers(env):
    layer_model = env['stock.valuation.layer'].with_context(skip_warehouse_consistency_check=True)
    layers = layer_model.search([
        ('quantity', '>', 0),
        ('origin_valuation_layer_id', '=', False),
    ])
    count = 0
    for layer in layers:
        vals = {}
        if not layer.origin_remaining_qty:
            vals['origin_remaining_qty'] = layer.quantity
        if not layer.origin_remaining_value:
            vals['origin_remaining_value'] = layer.value
        if vals:
            layer.write(vals)
            count += 1
    return count


def _backfill_transfer_position_layers(env):
    layer_model = env['stock.valuation.layer'].with_context(skip_warehouse_consistency_check=True)
    move_model = env['stock.move']
    unresolved_count = 0
    updated_count = 0

    transfer_layers = layer_model.search([
        ('quantity', '>', 0),
        ('origin_valuation_layer_id', '=', False),
        ('stock_move_id', '!=', False),
    ], order='stock_move_id, create_date, id')

    for layer in transfer_layers:
        move = layer.stock_move_id
        if not move or not move.location_id or not move.location_dest_id:
            continue

        source_wh = move.location_id.warehouse_id
        dest_wh = move.location_dest_id.warehouse_id
        if not (source_wh and dest_wh and source_wh.id != dest_wh.id):
            continue

        origin_layer = _guess_origin_layer(env, move_model, layer, move, source_wh)
        if not origin_layer:
            unresolved_count += 1
            _logger.warning(
                "Could not backfill origin layer for SVL %s (move %s, product %s)",
                layer.id, move.name, layer.product_id.display_name
            )
            continue

        vals = {
            'origin_valuation_layer_id': origin_layer.id,
            'source_warehouse_id': source_wh.id,
            'transfer_move_id': move.id,
            'is_position_layer': True,
        }
        layer.write(vals)
        updated_count += 1

    return updated_count, unresolved_count


def _guess_origin_layer(env, move_model, position_layer, move, source_wh):
    layer_model = env['stock.valuation.layer']
    negative_layers = layer_model.search([
        ('stock_move_id', '=', move.id),
        ('quantity', '<', 0),
        ('warehouse_id', '=', source_wh.id),
        ('origin_valuation_layer_id', '!=', False),
    ], order='id asc')
    if negative_layers:
        return negative_layers[0].origin_valuation_layer_id

    candidates = layer_model.search([
        ('product_id', '=', position_layer.product_id.id),
        ('warehouse_id', '=', source_wh.id),
        ('quantity', '>', 0),
        ('create_date', '<=', position_layer.create_date),
    ], order='create_date asc, id asc')
    if not candidates:
        return False

    same_cost = candidates.filtered(
        lambda layer: abs((layer.unit_cost or 0.0) - (position_layer.unit_cost or 0.0)) < 0.0001
    )
    return (same_cost[:1] or candidates[:1]) and (same_cost[:1] or candidates[:1])[0]
