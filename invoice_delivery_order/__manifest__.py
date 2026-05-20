# -*- coding: utf-8 -*-
{
    'name': 'Invoice Delivery Order',
    'version': '17.0.1.1.0',
    'category': 'Accounting',
    'summary': 'Link Delivery Orders to Customer Invoices and show on document',
    'description': """
Invoice Delivery Order
======================
Add a Delivery Order (stock.picking) selector on Customer Invoice.
Smart-filter shows only DOs from the related Sales Orders.
The DO number is displayed on the printed invoice PDF.
    """,
    'author': 'AI-DEV-Module-Odoo17',
    'website': 'https://github.com/apcball/AI-DEV-Module-Odoo17',
    'license': 'LGPL-3',
    'depends': [
        'account',
        'stock',
        'sale',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/invoice_view.xml',
        'report/invoice_report.xml',
    ],
    'assets': {},
    'application': True,
    'installable': True,
    'auto_install': False,
}
