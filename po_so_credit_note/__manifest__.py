# -*- coding: utf-8 -*-
{
    'name': 'PO & SO Credit Note',
    'version': '17.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Create credit notes from PO and SO with negative lines',
    'description': """
        PO & SO Credit Note Module
        ==========================

        Features:
        * Create credit notes from Purchase Orders (PO) for negative quantity lines
        * Create credit notes from Sale Orders (SO) for refundable lines
        * Wizard interface to select which lines to include in credit note
        * Automatic linking between credit notes and source orders
    """,
    'author': 'AI-DEV-Module-Odoo17',
    'website': 'https://github.com/AI-DEV-Module-Odoo17',
    'depends': ['purchase', 'sale', 'account'],
    'data': [
        'security/ir.model.access.csv',
        'views/account_move_views.xml',
        'views/purchase_order_views.xml',
        'views/sale_order_views.xml',
        'wizards/po_credit_note_wizard_views.xml',
        'wizards/so_credit_note_wizard_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
