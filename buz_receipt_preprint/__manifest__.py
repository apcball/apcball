{
    'name': 'Pre-printed Receipt',
    'version': '17.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Pre-printed Receipt Form',
    'description': """
        This module adds support for printing receipts on pre-printed forms.
        Features:
        - Custom receipt layout for pre-printed forms
        - Configurable receipt format
        - Support for Thai language
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'depends': ['base', 'account'],
    'data': [
        'security/ir.model.access.csv',
        'views/receipt_views.xml',
        'reports/receipt_templates.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}