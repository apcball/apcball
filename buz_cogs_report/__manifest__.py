# -*- coding: utf-8 -*-
{
    'name': 'Actual COGS Report',
    'summary': 'Actual cost of goods sold from FIFO valuation layers (by month, warehouse, product)',
    'description': """
Reads stock.valuation.layer directly (book of record under manual_periodic):
- Sales: layers of moves that go to a customer location (COGS +)
- Returns: layers of moves that come from a customer location (COGS -)
Period bucket uses accounting_date (Asia/Bangkok). Includes all history;
filter by date in the UI (opening cutoff 2026-03-30 is not applied).
    """,
    'license': 'LGPL-3',
    'author': 'APC Ball',
    'category': 'Warehouse',
    'version': '17.0.1.0.0',
    'depends': ['stock', 'stock_account', 'stock_fifo_by_location', 'buz_dispatch_document'],
    'data': [
        'security/ir.model.access.csv',
        'views/buz_cogs_report_views.xml',
        'views/buz_cogs_export_wizard_views.xml',
    ],
    'installable': True,
}
