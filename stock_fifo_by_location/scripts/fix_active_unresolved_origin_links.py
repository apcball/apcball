# -*- coding: utf-8 -*-
"""
Fix active unresolved origin links left by migration 17.0.1.2.8.

Usage in Odoo shell:
    exec(open("/opt/instance1/odoo17/custom-addons/stock_fifo_by_location/scripts/fix_active_unresolved_origin_links.py").read())
    fix_active_unresolved_origin_links(env, dry_run=True)
    fix_active_unresolved_origin_links(env, dry_run=False)
"""


def _guess_origin_layer(layer_model, position_layer, move, source_wh):
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
        ('origin_valuation_layer_id', '=', False),
    ], order='create_date asc, id asc')
    if not candidates:
        return False

    active_origin = candidates.filtered(lambda layer: (layer.origin_remaining_qty or 0.0) > 0)
    if active_origin:
        candidates = active_origin

    same_cost = candidates.filtered(
        lambda layer: abs((layer.unit_cost or 0.0) - (position_layer.unit_cost or 0.0)) < 0.0001
    )
    if same_cost:
        return same_cost[0]

    earlier = candidates.filtered(lambda layer: layer.create_date and layer.create_date <= position_layer.create_date)
    if earlier:
        return earlier[-1]

    return candidates[0]


def _find_active_transfer_layers_without_origin(env):
    layer_model = env['stock.valuation.layer'].with_context(skip_warehouse_consistency_check=True)
    return layer_model.search([
        ('quantity', '>', 0),
        ('remaining_qty', '>', 0),
        ('origin_valuation_layer_id', '=', False),
        ('stock_move_id', '!=', False),
    ], order='stock_move_id, create_date, id')


def fix_active_unresolved_origin_links(env, dry_run=True):
    layer_model = env['stock.valuation.layer'].with_context(skip_warehouse_consistency_check=True)
    layers = _find_active_transfer_layers_without_origin(env)

    print('Active transfer layers without origin:', len(layers))
    fixed = 0
    unresolved = 0
    items = []

    for layer in layers:
        move = layer.stock_move_id
        if not move or not move.location_id or not move.location_dest_id:
            continue
        source_wh = move.location_id.warehouse_id
        dest_wh = move.location_dest_id.warehouse_id
        if not (source_wh and dest_wh and source_wh.id != dest_wh.id):
            continue

        origin_layer = _guess_origin_layer(layer_model, layer, move, source_wh)
        item = {
            'svl_id': layer.id,
            'product': layer.product_id.default_code or layer.product_id.display_name,
            'remaining_qty': layer.remaining_qty,
            'move': move.name,
            'picking': move.picking_id.name if move.picking_id else None,
            'source_wh': source_wh.display_name,
            'dest_wh': dest_wh.display_name,
            'origin_id': origin_layer.id if origin_layer else None,
        }
        items.append(item)
        print(item)

        if not origin_layer:
            unresolved += 1
            continue

        if dry_run:
            continue

        layer.write({
            'origin_valuation_layer_id': origin_layer.id,
            'source_warehouse_id': source_wh.id,
            'transfer_move_id': move.id,
            'is_position_layer': True,
        })
        fixed += 1

    if not dry_run:
        env.cr.commit()
    print('Fixed:', fixed)
    print('Still unresolved:', unresolved)
    return {'count': len(items), 'fixed': fixed, 'unresolved': unresolved, 'items': items}
