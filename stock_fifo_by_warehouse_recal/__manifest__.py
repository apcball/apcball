# -*- coding: utf-8 -*-
{
    'name': 'FIFO Queue Repair by Warehouse',
    'version': '17.0.5.0.0',
    'category': 'Inventory/Stock',
    'author': 'APC Ball',
    'website': 'https://github.com/apcball/apcball',
    'license': 'LGPL-3',
    'depends': [
        'stock',
        'stock_account',
        'stock_fifo_by_location',
    ],
    'data': [
        'security/fifo_recal_security.xml',
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'views/fifo_recalculation_wizard_views.xml',
        'views/fifo_recalculation_backup_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
    'description': '''
FIFO Queue Repair by Warehouse
==============================

Corrects the FIFO queue state stored on stock.valuation.layer, one warehouse at
a time, by replaying the FIFO engine over the layers that already exist.

What it writes
--------------
`remaining_qty` and `remaining_value`, and nothing else. It never deletes a
layer, never creates one, and never rewrites `value`.

Why it works that way
---------------------
stock.valuation.layer is the sole book of record for stock value here: product
categories are FIFO + manual_periodic, so most layers carry no journal entry and
a wrong number would never be contradicted by accounting.

Version 3 and earlier deleted layers in a date range and rebuilt them from
stock.move. That could not work on this database. Landed cost, manual
revaluation and position layers have no stock move behind them, so a rebuild
deleted them and had nothing to recreate them from. It also stamped a fresh
create_date on every recreated layer, which is the FIFO ordering key, scrambling
the queue it was meant to fix.

Safety
------
- Dry run by default; Apply is a separate, confirmed step.
- The FIFO replay lives on stock.valuation.layer and is shared with the wizard
  in stock_fifo_by_location, so the two tools cannot disagree.
- A mismatch gate refuses to apply when the replay disagrees with too much of
  stored state — a replay that cannot reproduce the data cannot correct it.
- Product/warehouse pairs are skipped when the queue was reordered by a
  backdating tool, when FIFO ran short, or when any layer is locked.
- The backup is mandatory. If it cannot be written in full, nothing is written.
  Rollback restores the two columns exactly.
- Outgoing `value` differences are measured and reported for a human to judge.
  Rewriting them would fabricate COGS.
- The scheduled action reports and emails; it does not apply.

Access
------
Restricted to the `FIFO Repair` group, which is empty on install and is not
granted by being a stock manager. Both the menus and the actions are gated.
    ''',
}
