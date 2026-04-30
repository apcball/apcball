# -*- coding: utf-8 -*-
{
    'name': 'POS Lite',
    'version': '17.0.1.0.0',
    'category': 'Sales',
    'summary': 'Lightweight form-based order entry for phone, LINE, and walk-in orders',
    'description': """
POS Lite
========
Simple form-based order entry for phone, LINE, walk-in, and other manual orders.
Creates invoice, stock picking, and printable receipt from a lightweight backend form.
    """,
    'author': 'AI-DEV-Module-Odoo17',
    'website': 'https://github.com/apcball/AI-DEV-Module-Odoo17',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'contacts',
        'product',
        'stock',
        'account',
        'sale_management',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequence_data.xml',
        'report/receipt_report.xml',
        'views/pos_order_view.xml',
        'views/pos_config_view.xml',
        'views/menu.xml',
        'wizard/payment_wizard_view.xml',
        'wizard/return_wizard_view.xml',
    ],
    'assets': {},
    'application': True,
    'installable': True,
    'auto_install': False,
}
