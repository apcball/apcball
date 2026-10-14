# -*- coding: utf-8 -*-
{
    'name': 'BG/RBG Loan and Return',
    'version': '17.0.1.1.0',
    'category': 'Inventory/Operations',
    'summary': 'Create linked loan and return stock transfers',
    'description': 'Dedicated workflow for BG loan and RBG return transfers.',
    'author': 'Mogen Co.',
    'license': 'LGPL-3',
    'depends': ['stock'],
    'assets': {
        'web.assets_backend': [
            'buz_loan_return/static/src/js/bg_document_list_controller.js',
            'buz_loan_return/static/src/js/bg_forecast.js',
            'buz_loan_return/static/src/xml/bg_forecast.xml',
            'buz_loan_return/static/src/xml/bg_document_list_buttons.xml',
        ],
    },
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'views/loan_return_views.xml',
        'views/stock_picking_views.xml',
        'wizard/create_loan_return_views.xml',
        'views/loan_return_menus.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}