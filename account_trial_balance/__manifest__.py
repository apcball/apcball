# -*- coding: utf-8 -*-
{
    'name': 'Trial Balance Report',
    'version': '17.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'งบทดลอง (Trial Balance Report)',
    'description': """
        Trial Balance Report
        =====================
        * Select date range, journals, and target moves
        * Print PDF report grouped by account type
        * Export to Excel with formatted layout
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'account',
        'web',
    ],
    'data': [
        'security/ir.model.access.csv',
        'wizard/trial_balance_wizard_view.xml',
        'report/trial_balance_report.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
