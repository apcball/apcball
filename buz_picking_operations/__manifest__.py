# __manifest__.py
{
    'name': 'Custom Picking Operations Report',
    'version': '17.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Customize picking operations report',
    'description': """
        This module customizes the picking operations report in Odoo 17.
        Features:
        - Enhanced layout for picking operations
        - Additional information on reports
        - Customized design following Odoo 17 standards
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'depends': ['stock'],
    'data': [
        'security/ir.model.access.csv',
        'reports/picking_operations_report.xml',
        'views/stock_picking_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}