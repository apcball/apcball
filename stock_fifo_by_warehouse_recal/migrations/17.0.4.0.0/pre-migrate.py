# -*- coding: utf-8 -*-
"""Drop the columns of the delete-and-rebuild design.

Removing a field in Odoo leaves its column behind. For date_from / date_to that
matters: they were `required`, so the column is still NOT NULL and every insert
into the table would fail once the field no longer supplies a value.

The tables are empty on both MOG_DEV and MOG_LIVE (verified 2026-08-28), so
dropping the columns loses nothing.
"""

import logging

_logger = logging.getLogger(__name__)

OBSOLETE = {
    'fifo_recalculation_wizard': [
        'date_from', 'date_to', 'clear_old_layers', 'lock_after_recal',
        'batch_size', 'progress_percent', 'progress_message',
    ],
    'fifo_recalculation_backup': [
        'date_from', 'date_to',
    ],
    'fifo_recalculation_backup_line': [
        'layer_data',
    ],
    'fifo_recalculation_config': [
        'date_from', 'date_to', 'clear_old_layers', 'lock_after_recal',
        'batch_size', 'auto_apply',
    ],
}


def migrate(cr, version):
    if not version:
        return

    for table, columns in OBSOLETE.items():
        cr.execute("SELECT to_regclass(%s)", (table,))
        if not cr.fetchone()[0]:
            continue
        for column in columns:
            cr.execute(
                'ALTER TABLE "%s" DROP COLUMN IF EXISTS "%s"' % (table, column))
        _logger.info('stock_fifo_by_warehouse_recal: dropped %s from %s',
                     ', '.join(columns), table)

    # ir.model.fields rows for the removed fields are cleaned up by the
    # registry after the upgrade; nothing to do here.
