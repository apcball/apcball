{
    'name': 'Partner Movement Excel Report',
    'version': '17.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Partner receivable, payable and accrual movement Excel report',
    'license': 'LGPL-3',
    'depends': ['account', 'report_xlsx'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/partner_movement_wizard_views.xml',
        'report/partner_movement_report.xml',
    ],
    'installable': True,
    'application': False,
}
