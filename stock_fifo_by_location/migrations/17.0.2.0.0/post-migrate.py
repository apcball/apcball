# -*- coding: utf-8 -*-
"""
Migration script for version 17.0.2.0.0

Fix position layer origin links for landed cost support.

Problem:
  Position layers (is_position_layer=True) have origin_valuation_layer_id
  pointing to negative transfer-out layers instead of the original receipt layer.
  This prevents get_valuation_lines() from finding position layers when
  applying landed costs on receipt pickings whose goods have been fully transferred.

Fix:
  Re-link each position layer to the correct receipt layer (root origin) by
  tracing the transfer move back to the source warehouse and finding the
  positive layer with origin_valuation_layer_id = False that was consumed.

Also:
  Removed the valuation_method != 'real_time' filter in get_valuation_lines()
  so that manual_periodic products can also have landed costs applied,
  matching Odoo core behaviour which only checks cost_method.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Migration to version 17.0.2.0.0 — Fix position layer origin links.
    """
    _logger.info("=" * 80)
    _logger.info("🔄 Migrating to 17.0.2.0.0: Fix position layer origin links for landed cost")
    _logger.info("=" * 80)

    # Step 1: Find all position layers whose origin points to a negative layer
    cr.execute("""
        SELECT pos.id        AS pos_id,
               pos.product_id,
               neg.id        AS wrong_origin_id,
               neg.quantity  AS neg_qty,
               sm.location_id AS source_location_id
        FROM stock_valuation_layer pos
        JOIN stock_valuation_layer neg ON pos.origin_valuation_layer_id = neg.id
        JOIN stock_move sm ON pos.stock_move_id = sm.id
        WHERE pos.is_position_layer = true
          AND neg.quantity < 0
        ORDER BY pos.id
    """)
    rows = cr.fetchall()
    _logger.info("Found %d position layers with wrong origin (pointing to negative layer)", len(rows))

    if not rows:
        _logger.info("✅ No migration needed — all position layers already correct")
        return

    fixed = 0
    for pos_id, product_id, wrong_origin_id, neg_qty, source_location_id in rows:
        # Find the source warehouse from the location
        cr.execute("SELECT warehouse_id FROM stock_location WHERE id = %s", (source_location_id,))
        wh_row = cr.fetchone()
        if not wh_row or not wh_row[0]:
            _logger.warning("  PL %d: SKIP — no warehouse for source location %s", pos_id, source_location_id)
            continue
        source_wh_id = wh_row[0]

        # Find the correct receipt layer: positive, root (no origin), at source warehouse,
        # same product, created before the wrong origin, and still has origin_remaining_qty > 0
        cr.execute("""
            SELECT svl.id
            FROM stock_valuation_layer svl
            WHERE svl.product_id = %s
              AND svl.warehouse_id = %s
              AND svl.quantity > 0
              AND svl.origin_valuation_layer_id IS NULL
              AND svl.origin_remaining_qty > 0
              AND svl.create_date <= (
                  SELECT create_date FROM stock_valuation_layer WHERE id = %s
              )
              AND svl.id != %s
            ORDER BY svl.create_date ASC
            LIMIT 1
        """, (product_id, source_wh_id, wrong_origin_id, pos_id))
        correct_row = cr.fetchone()

        if not correct_row:
            _logger.warning("  PL %d: SKIP — no receipt candidate (product=%s, src_wh=%s)", pos_id, product_id, source_wh_id)
            continue

        correct_origin_id = correct_row[0]
        cr.execute(
            "UPDATE stock_valuation_layer SET origin_valuation_layer_id = %s WHERE id = %s",
            (correct_origin_id, pos_id),
        )
        _logger.info("  PL %d: origin %d → %d (receipt layer)", pos_id, wrong_origin_id, correct_origin_id)
        fixed += 1

    _logger.info("")
    _logger.info("✅ Fixed %d / %d position layer origin links", fixed, len(rows))
    _logger.info("=" * 80)
    _logger.info("✅ Migration to 17.0.2.0.0 complete!")
    _logger.info("=" * 80)
