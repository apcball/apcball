# -*- coding: utf-8 -*-
{
    'name': 'Direct Print Epson',
    'version': '17.0.1.0.0',
    'category': 'Technical/Printing Integration',
    'summary': 'Direct printing to Epson printers via Local Print Agent',
    'author': 'buz',
    'license': 'LGPL-3',
    'depends': ['base', 'account', 'stock'],
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'views/epson_config_view.xml',
        'views/account_move_view.xml',
        'views/stock_picking_view.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'images': ['static/description/banner.png'],
}