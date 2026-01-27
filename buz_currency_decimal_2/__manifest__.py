# -*- coding: utf-8 -*-
{
    'name': 'Currency Decimal 2 Places',
    'version': '17.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Set currency decimal places to 2 automatically',
    'description': """
        This module automatically sets decimal places to 2 and rounding to 0.01
        for THB currency when installed.
        
        Note: Only works if the currency hasn't been used in accounting entries yet.
        For existing databases, you may need to use the manual action or 
        update the currency before creating any accounting entries.
    """,
    'author': 'Buz',
    'depends': ['base'],
    'data': [
        'views/res_currency_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
