# -*- coding: utf-8 -*-
{
    'name': 'Manufacturing Backdate/Forcedate',
    'version': '17.0.2.0.0',
    'category': 'Manufacturing',
    'summary': 'Allow backdating for Manufacturing Orders and Unbuild Orders with remark support',
    'description': """
Manufacturing Backdate Module
=============================
Add backdate and remark fields to Manufacturing Orders and Unbuild Orders.
Update stock moves, product moves, inventory valuation, and journal entries with backdate.
Wizard to set backdate after validation (Done state).
Does not affect normal MO/Unbuild confirmation logic.
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
        'views/mrp_unbuild_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
