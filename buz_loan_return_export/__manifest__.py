# -*- coding: utf-8 -*-
{
    'name': 'Loan and Return Export',
    'version': '17.0.1.0.0',
    'category': 'Inventory/Reporting',
    'summary': 'Export loan and return picking details to Excel',
    'author': 'Mogen Co.',
    'license': 'LGPL-3',
    'depends': [
        'stock',
        'report_xlsx',
        'buz_inventory_delivery_report',
    ],
    'data': [
        'security/ir.model.access.csv',
        'report/loan_return_export_report.xml',
        'views/loan_return_export_wizard_views.xml',
        'views/loan_return_export_menu.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}

