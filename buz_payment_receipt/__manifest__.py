{
    'name': 'buz Payment Receipt',
    'version': '17.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Custom Modern Payment Receipt Report',
    'description': """
        This module replaces the default payment receipt with a modern design.
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'depends': ['account'],
    'data': [
        'security/ir.model.access.csv',
        'reports/payment_receipt_template.xml',
        'reports/payment_receipt_report.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}