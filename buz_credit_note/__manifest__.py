{
    'name': 'Buz Credit Note',
    'version': '1.0',
    'category': 'Accounting',
    'summary': 'Custom Credit Note Report for Thai Companies',
    'description': """
        Custom Credit Note report with Thai language support
        and company-specific formatting
    """,
    'author': 'Your Name',
    'website': 'https://www.yourwebsite.com',
    'depends': ['account'],
    'data': [
        'security/ir.model.access.csv',
        'data/sequence_data.xml',
        'report/credit_note_report.xml',  # ต้องโหลดก่อน views
        'views/credit_note_views.xml',
    ],
    'assets': {
        'web.report_assets_common': [
            
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}