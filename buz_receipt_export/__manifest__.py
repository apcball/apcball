{
    'name': 'Receipt Voucher Report',
    'version': '17.0.1.0.0',
    'category': 'Accounting/Reporting',
    'summary': 'Export accounting receipt voucher details to XLSX',
    'description': """
        Receipt Voucher Report
        ======================
        Export one row per invoice line linked to a receipt voucher.
    """,
    'author': 'Mogen Co.',
    'license': 'LGPL-3',
    'depends': ['account', 'report_xlsx', 'buz_accounting_addon'],
    'data': [
        'security/ir.model.access.csv',
        'report/receipt_voucher_report.xml',
        'wizard/receipt_export_wizard_view.xml',
        'views/receipt_export_menu.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
