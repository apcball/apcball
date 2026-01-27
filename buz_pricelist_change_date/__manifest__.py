# -*- coding: utf-8 -*-
{
    'name': 'Pricelist Change Date',
    'version': '17.0.1.0.0',
    'category': 'Sale',
    'summary': 'Allow users to quickly change the start and end dates of all price rules in a pricelist',
    'description': """
        This module allows users to quickly change the start and end dates of all price rules in a pricelist from the pricelist form view.
        
        Features:
        - Add a button in the pricelist form view to change dates
        - Wizard to update all price rule dates at once
        - Validation to ensure end date is not earlier than start date
    """,
    'author': 'BUZ',
    'website': 'https://www.buz.com',
    'license': 'LGPL-3',
    'depends': [
        'product',
        'sale_management',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/product_pricelist_views.xml',
        'views/pricelist_change_date_wizard_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}