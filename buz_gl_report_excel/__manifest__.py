{
    'name': 'Buz General Ledger Report Excel',
    'version': '17.0.1.0.0',
    'summary': 'General Ledger and Aged Reports with Excel Export',
    'description': """
        General Ledger Report similar to standard but with specific layout and Excel export.
        Aged Partner Report, Aged Receivable Report, and Aged Payable Report for aging analysis.
        Optimized for large data.
    """,
    'category': 'Accounting',
    'author': 'Antigravity',
    'depends': ['account', 'report_xlsx'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/gl_report_wizard_view.xml',
        'wizard/aged_partner_wizard_view.xml',
        'wizard/aged_receivable_wizard_view.xml',
        'wizard/aged_payable_wizard_view.xml',
        'reports/gl_report.xml',
        'reports/gl_report_template.xml',
        'reports/aged_partner_report.xml',
        'reports/aged_reports.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
