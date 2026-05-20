{
    'name': 'Buz TR Bank Export',
    'version': '17.0.1.0.0',
    'summary': 'Document of transfer money abroad and Vendor Payment Generation',
    'category': 'Accounting/Accounting',
    'author': 'Antigravity',
    'depends': ['account'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/sequence_data.xml',
        'views/bank_export_views.xml',
        'report/bank_export_report.xml',
        'report/bank_export_report_template.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
