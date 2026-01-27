# -*- coding: utf-8 -*-
{
    'name': 'Manufacturing Backdate/Forcedate',
    'version': '17.0.1.0.0',
    'category': 'Manufacturing',
    'summary': 'Allow backdating for Manufacturing Orders with remark support',
    'description': """
Manufacturing Backdate Module
=============================
Add backdate and remark fields to Manufacturing Orders.
Update stock moves, product moves, inventory valuation, and journal entries with backdate.
Wizard to set backdate before validation.
Does not affect normal MO confirmation logic.
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'license': 'LGPL-3',
    'depends': [
        'mrp',
        'stock',
        'stock_account',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'wizard/mrp_backdate_wizard_views.xml',
        'views/mrp_production_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
