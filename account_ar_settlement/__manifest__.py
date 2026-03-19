# -*- coding: utf-8 -*-
{
    'name': 'AR Settlement Engine',
    'version': '17.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Advanced Accounts Receivable Settlement with VAT grouping, trade channels, credit notes, and payment difference handling',
    'description': """
AR Settlement Engine
====================

Advanced Accounts Receivable Settlement Engine for Odoo 17.

Key Features:
- Customer payment allocation with FIFO auto-allocate
- Credit note allocation
- VAT group settlement (settle across branches with same VAT ID)
- Trade channel filtering
- Bank fee support
- Payment difference handling (overpayment / underpayment)
- Configurable difference account (default: 214100 Accrued Expenses)
- Posting preview before confirmation

Menu Location:
    Accounting → Customers → AR Settlement
    """,
    'author': 'Custom',
    'license': 'LGPL-3',
    'depends': [
        'account',
        'mail',
        'sale',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'views/ar_settlement_views.xml',
        'views/ar_settlement_menu.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}
