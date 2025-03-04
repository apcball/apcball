{
    'name': 'Custom Purchase Order Report',
    'version': '17.0.1.0.0',
    'category': 'Purchase',
    'summary': 'Custom Purchase Order PDF Report',
    'description': """
        Custom PDF report for purchase orders with discount calculation
    """,
    'depends': ['base', 'purchase'],
    'data': [
        'security/ir.model.access.csv',
        'reports/purchase_order_report.xml',
        'views/report_menu.xml',
    ],
    'assets': {
        'web.report_assets_common': [
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}