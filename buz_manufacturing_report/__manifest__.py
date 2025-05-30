# -*- coding: utf-8 -*-
{
    'name': 'Manufacturing Reports',
    'version': '17.0.1.0.0',
    'category': 'Manufacturing',
    'summary': 'Advanced PDF reports for manufacturing operations',
    'description': """
        This module adds advanced PDF reports for manufacturing operations:
        - Production Order Report
        - Work Order Report
        - Manufacturing Performance Report
        - Material Consumption Report
    """,
    'author': 'Buz',
    'website': 'https://www.example.com',
    'depends': ['mrp', 'stock', 'product', 'report_xlsx', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'views/manufacturing_report_views.xml',
        'wizard/manufacturing_report_wizard_views.xml',
        'report/manufacturing_report_templates.xml',
        'report/report_action.xml',
        'report/production_order_report.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'buz_manufacturing_report/static/src/css/style.css',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}