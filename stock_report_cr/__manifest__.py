# -*- coding: utf-8 -*-
# Part of Odoo Module Developed by CandidRoot Solutions Pvt. Ltd.
# See LICENSE file for full copyright and licensing details.
{
    'name': 'buz Stock Report Based on Location',
    'version': '17.0.0.1',
    'category': 'Inventory',
    'author': 'CandidRoot Solutions Pvt. Ltd.',
    'website': 'https://candidroot.com/',
    'summary': 'This module allows user to print a stock report for a location whether location is internal/view/inventory, production/scrapped location. This module will give you the product wise in stock, out stock and the balance of location between a period.',

    'depends': ['base', 'stock'],
    'description': """
    """,
    'data': [
        'security/ir.model.access.csv',
        'wizard/stock_report.xml',
        'report/stock_report.xml',
        'report/stock_template.xml'
    ],
    'demo': [
    ],
    'images': ['static/description/banner.png'],
    'live_test_url': 'https://youtu.be/3MFwK9KoKvo',
    'installable': True,
    'auto_install': False,
    'application': True,
    'license': 'LGPL-3',
}
