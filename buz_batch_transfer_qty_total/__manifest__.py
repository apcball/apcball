# -*- coding: utf-8 -*-
{
    'name': 'Batch Transfer Quantity Total',
    'version': '17.0.1.0.0',
    'category': 'Inventory',
    'summary': 'Add total quantity summary to batch transfers',
    'description': """
This module adds a total quantity field to batch transfers in Odoo 17.
It displays the sum of all quantities from transfers within a batch
as a summary at the bottom of the batch transfer form.

Features:
- Displays total quantity for all transfers in a batch
- Shows in both form view and as summary in tree view
- Compatible with Odoo 17 Community & Enterprise
    """,
    'author': 'BUZ',
    'website': 'https://www.buz.co.th',
    'depends': [
        'stock',
        'stock_picking_batch',
    ],
    'data': [
        'views/stock_picking_batch_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'LGPL-3',
    'images': ['static/description/main.png'],
}