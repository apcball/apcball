# -*- coding: utf-8 -*-
{
    'name': 'Purchase Receipt Exchange Rate',
    'version': '17.0.1.2.0',
    'category': 'Warehouse',
    'summary': 'Set a manual Exchange Rate Date/Rate on a Receipt and use it for Stock Valuation',
    'description': """
Purchase Receipt Exchange Rate
===============================
Allows setting a custom Exchange Rate Date and Exchange Rate on a foreign
currency Receipt (stock.picking) coming from a Purchase Order, so that the
Stock Valuation Layer and its Accounting Entry use that rate instead of the
rate implied by the receipt processing date.

* Set Exchange Rate Date directly on the Purchase Order; confirming the PO
  copies it onto the created Receipt(s) and auto-fetches the rate
* Blocks "Submit for Review" (buz_po_portal) on foreign currency POs until
  Exchange Rate Date is set
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
        'buz_po_portal',
    ],
    'data': [
        'security/security.xml',
        'views/stock_picking_views.xml',
        'views/purchase_order_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
