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
        - Configurable print positions with validation
        - Font size controls
        - Quick setup wizard for adjustments
        - Background template support for alignment
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'depends': ['base', 'account'],
    'data': [
        'security/ir.model.access.csv',
        'data/receipt_print_config_data.xml',
        'views/receipt_print_config_views.xml',
        'wizard/receipt_print_quick_setup_views.xml',
        'views/receipt_views.xml',
        'reports/receipt_templates.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}