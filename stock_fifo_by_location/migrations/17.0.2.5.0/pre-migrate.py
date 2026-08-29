# -*- coding: utf-8 -*-
"""Let security.xml take the obsolete repair group back.

The group used to be declared inside `<data noupdate="1">` so an upgrade would
not reset its membership list. security.xml no longer sets `users`, so the
noupdate is pointless, and it is now actively in the way: it is what stops the
rename to "Stock Valuation Repair (obsolete)" from landing.

Dropping noupdate from the XML alone is not enough. convert.py's check reads
the data node, but ir.model.data carries its own stored `noupdate` column and
_load_records() checks that one too, so a record written once under noupdate
stays frozen until the stored flag is cleared. This has to happen before the
data files load, hence pre-migrate rather than post-.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    cr.execute("""
        UPDATE ir_model_data
        SET noupdate = false
        WHERE module = 'stock_fifo_by_location'
          AND model = 'res.groups'
          AND name = 'group_stock_valuation_repair'
          AND noupdate IS TRUE
    """)
    _logger.info('cleared noupdate on the Stock Valuation Repair group '
                 '(%s row) so security.xml can rename it', cr.rowcount)
