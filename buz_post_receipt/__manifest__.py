{
    'name': 'Post Receipt Report',
    'version': '17.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Custom Post Receipt Report for Accounting',
    'description': """
        This module adds a custom post receipt report in accounting module.
        Features:
        - Custom post receipt template
        - Print button in payment form view
        - Detailed payment information
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'depends': ['account'],
    'data': [
        'security/ir.model.access.csv',
        'reports/post_receipt_report.xml',
        'views/invoice_receipt_view.xml',
    ],
    'assets': {
        'web.report_assets_common': [
            'buz_post_receipt/static/src/scss/fonts.scss',
            'buz_post_receipt/static/src/scss/post_receipt.scss',
        ],  # Added missing closing bracket for the list
    },  # Added missing closing bracket for 'assets'
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}