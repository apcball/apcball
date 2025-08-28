# -*- coding: utf-8 -*-
{
    'name': 'Petty Cash Management',
    'version': '17.0.0.1',
    'sequence': 7,
    'category': 'Accounting',
    'summary': 'Petty cash transaction management',
    'author': 'Al-haj Hashim',
    'website': 'https://www.linkedin.com/in/alhaj-hashim',
    'depends': ['account', 'analytic', 'hr', 'hr_expense'],
    'data': [
            'security/ir.model.access.csv',
            'data/data.xml',
            'views/menuitem.xml',
            'wizard/petty_cash_operation_view.xml',
            'views/petty_cash_request_view.xml',
            'views/petty_cash_settelement_view.xml'
        ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
    'images': ['static/description/logo.png'],
}

