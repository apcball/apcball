{
    'name': 'Buz Proforma Invoice',
    'version': '1.0',
    'category': 'Sales',
    'summary': 'Module to manage proforma invoices',
    'description': """
    This module adds the functionality to create and print proforma invoices based on sale orders.
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'depends': ['base', 'sale', 'account'],
    'data': [
        'security/ir.model.access.csv',
        'reports/proforma_invoice_report.xml',
    ],
    'assets': {
        'web.report_assets_common': [
            'buz_proforma_invoice/static/src/scss/proforma_invoice_style.scss',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}