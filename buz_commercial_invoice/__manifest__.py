{
    'name': 'Custom Commercial Invoice Report',
    'version': '17.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Customize Commercial Invoice Report',
    'description': """
        Customization for Commercial Invoice Report in Accounting module.
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'depends': [
        'base',
        'account',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'report/paperformat.xml',
        'report/report_action.xml',
        'report/commercial_invoice_report.xml',
        'views/account_move_view.xml',
        
    ],
    'assets': {
        'web.assets_backend': [
            # Add your CSS/JS files if needed
        ],
    },
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
    'auto_install': False,
}