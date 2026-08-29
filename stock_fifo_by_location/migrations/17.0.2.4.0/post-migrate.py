# -*- coding: utf-8 -*-
"""Backfill stock_valuation_layer.accounting_date.

The column is new, so every existing layer has NULL. Seed it with the same
expression the valuation reports were computing on the fly:

    COALESCE(landed_cost.date, stock_move.date, svl.create_date)

Plain SQL rather than an ORM write: this touches every layer on the database
(~1.5M rows on production) and the value is derived, so there is nothing for
compute methods or constraints to add.

create_date is deliberately left alone — it is the ordering key of the FIFO
candidate queue in _run_fifo().
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    cr.execute("""
        UPDATE stock_valuation_layer svl
        SET accounting_date = COALESCE(
                lc.date::timestamp,
                sm.date,
                svl.create_date
            )
        FROM stock_valuation_layer l
            LEFT JOIN stock_move sm ON sm.id = l.stock_move_id
            LEFT JOIN stock_landed_cost lc ON lc.id = l.stock_landed_cost_id
        WHERE l.id = svl.id
          AND svl.accounting_date IS NULL
    """)
    _logger.info("accounting_date backfilled on %s valuation layers", cr.rowcount)
