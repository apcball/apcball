# -*- coding: utf-8 -*-
{
    'name': 'buz All In One Backdate Advanced',
    'version': '17.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Allow backdating for invoices, payments, journal entries and other documents',
    'description': """
All In One Backdate Advanced
============================

This module provides comprehensive backdating functionality for various Odoo documents:

Features:
---------
* Backdate Customer Invoices
* Backdate Vendor Bills
* Backdate Customer Payments
* Backdate Vendor Payments
* Backdate Journal Entries
* Backdate Bank Statements
* Backdate Purchase Orders
* Backdate Sales Orders
* Backdate Inventory Moves
* User-based permissions for backdating
* Date validation and restrictions
* Audit trail for backdated documents

The module allows authorized users to modify dates on posted documents while maintaining proper audit trails and validation rules.
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'depends': [
        'base',
        'account',
        'sale',
        'purchase',
        'stock',
        'account_payment',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'views/backdate_log_views.xml',
        'views/account_move_views.xml',
        'views/account_payment_views.xml',
        'views/sale_order_views.xml',
        'views/purchase_order_views.xml',
        'views/stock_picking_views.xml',
        'views/res_config_settings_views.xml',
        'wizard/backdate_wizard_views.xml',
    ],
    'demo': [],
    'installable': True,
    'auto_install': False,
    'application': True,
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
    'price': 0,
    'currency': 'THB',
}