{
    'name': 'Purchase Order Monthly Report',
    'version': '17.0.1.0.0',
    'category': 'Purchases',
    'summary': 'Export purchase order details to Excel',
    'author': 'Mogen Co.',
    'license': 'LGPL-3',
    'depends': ['purchase', 'employee_purchase_requisition', 'buz_custom_partner'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/po_monthly_report_wizard_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
