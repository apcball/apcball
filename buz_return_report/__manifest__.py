{
    'name': 'BUZ Return Report',
    'version': '17.0.1.0.0',
    'category': 'Inventory/Reporting',
    'summary': 'Custom Return Slip Report',
    'description': """
        Customized Return Slip report for Odoo 17.
        - Thai-English bilingual format
        - Professional layout
        - Company details
        - Customer information
        - Product details
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'depends': ['stock', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'report/return_report.xml',
    ],
    'assets': {
        'web.report_assets_common': [
            '/buz_return_report/static/fonts/Sarabun-Bold.ttf',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}