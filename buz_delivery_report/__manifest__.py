{
    'name': 'Custom Delivery Report',
    'version': '17.0.1.0.0',
    'category': 'Inventory/Delivery',
    'summary': 'Customize delivery report template',
    'description': """
        This module customizes the delivery report template in Odoo.
        Features:
        - Custom delivery slip design
        - Additional information on delivery reports
        - Enhanced layout and formatting
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'depends': ['stock', 'delivery'],
    'data': [
        'security/ir.model.access.csv',
        'reports/delivery_report.xml',
        'views/report_menu.xml',
    ],
    'images': ['static/description/icon.png'],
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
    'auto_install': False,
}