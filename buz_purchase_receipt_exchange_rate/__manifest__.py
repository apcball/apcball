# -*- coding: utf-8 -*-
{
    'name': 'Purchase Receipt Exchange Rate',
    'version': '17.0.1.0.0',
    'category': 'Warehouse',
    'summary': 'Set a manual Exchange Rate Date/Rate on a Receipt and use it for Stock Valuation',
    'description': """
Purchase Receipt Exchange Rate
===============================
Allows setting a custom Exchange Rate Date and Exchange Rate on a foreign
currency Receipt (stock.picking) coming from a Purchase Order, so that the
Stock Valuation Layer and its Accounting Entry use that rate instead of the
rate implied by the receipt processing date.

* Adds "Foreign Currency Costing" section on the Receipt form
* "Get Exchange Rate" button pulls the Odoo currency rate at the chosen date
* "Recalculate Cost" button previews the estimated cost before Validate
* Purchase Order price is never modified
* Global res.currency.rate is never modified
* Only affects incoming PO receipts validated after this module is installed
    """,
    'author': 'Mogen Co.',
    'website': 'https://mogen.co.th',
    'license': 'LGPL-3',
    'depends': [
        'stock_account',
        'purchase_stock',
        'biz_receipt_transfer_cost',
    ],
    'data': [
        'security/security.xml',
        'views/stock_picking_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
