{
    'name': 'Buz General Ledger Report Excel',
    'version': '17.0.1.0.0',
    'summary': 'General Ledger Report with Excel Export',
    'description': """
        General Ledger Report similar to standard but with specific layout and Excel export.
        Optimized for large data.
    """,
    'category': 'Accounting',
    'author': 'Antigravity',
    'depends': ['account', 'report_xlsx'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/gl_report_wizard_view.xml',
        'reports/gl_report.xml',
        'reports/gl_report_template.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
