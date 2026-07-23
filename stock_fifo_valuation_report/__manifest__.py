# -*- coding: utf-8 -*-
{
    'name': "Stock FIFO Valuation Report",

    'summary': """
        Valuation report by warehouse sourced from FIFO stock.valuation.layer,
        with true per-layer detail (correct for MO consumption)""",

    'description': """
Stock FIFO Valuation Report
============================

Companion report to stock_fifo_by_location. Unlike imex_inventory_report
(which derives detail from stock_move + a per-move averaged unit cost),
this report reads stock.valuation.layer directly:

- Summary: opening / in / out / ending value per product x warehouse,
  cross-checked against sum(remaining_value) of still-open layers.
- Detail: one row per valuation layer, including remaining_qty,
  origin_remaining_qty and origin_valuation_layer_id, so MO component
  consumption can be traced to the exact FIFO layer/batch it drew from.
    """,
    "license": "LGPL-3",
    'author': "APC Ball",
    'category': 'Warehouse',
    'version': '17.0.1.0.0',

    'depends': ['base', 'stock', 'stock_account', 'product', 'stock_fifo_by_location'],

    'data': [
        'security/ir.model.access.csv',
        'reports/stock_fifo_valuation_report_views.xml',
        'reports/stock_fifo_valuation_details_report_views.xml',
        'wizard/stock_fifo_valuation_report_wizard_views.xml',
    ],
    "assets": {
        "web.assets_backend": [
            "stock_fifo_valuation_report/static/src/css/**/*",
        ],
    },
    "installable": True,
}
