{
    'name': 'Bank Statement Import',
    'version': '17.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Import bank statements with different bank profiles',
    'description': """
        This module allows users to:
        * Upload bank statements (.csv, xlsx)
        * Select bank profile for import
        * Convert bank statement to Odoo format
        * Import converted statements to Odoo
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'depends': ['account', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'data/bank_statement_profile_template.xml',
        'views/bank_statement_profile_views.xml',
        'views/bank_statement_upload_views.xml',
        'views/menu_views.xml',
        'wizards/import_bank_statement_view.xml',
    ],
    'demo': [
        'data/demo/bank_statement_demo.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}