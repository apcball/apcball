# -*- coding: utf-8 -*-
{
    'name': 'buz_advance_accounting',
    'summary': 'Advance expense accrual on Purchase Orders with reversal',
    'description': 'Post accrual journal entries from PO, keep a link, and allow reversal when creating vendor bill.',
    'version': '17.0.1.0.18',
    'author': 'apcball',
    'license': 'LGPL-3',
    'depends': ['purchase', 'account'],
    'data': [
        'security/ir.model.access.csv',
        'views/purchase_views.xml',
        'views/account_move_views.xml',
        'views/menu.xml',
        'wizards/advance_bill_wizard_views.xml',
    ],
    'assets': {},
    'icon': '/opt/instance1/odoo17/custom-addons/buz_advance_accounting/static/description/icon.png',
    'installable': True,
    'application': False,
}
