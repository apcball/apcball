{
    'name': 'BUZ Custom Quotation',
    'version': '17.0.1.0.0',
    'category': 'Sales',
    'summary': 'Custom Quotation Template',
    'description': """Custom Quotation form for BUZ""",
    'author': 'BUZ',
    'depends': [
        'sale',
        'sale_management',
        'web',
    ],
    'data': [
        'data/sequence.xml',
        'security/ir.model.access.csv',
        'report/sale_report_templates.xml',
        'report/sale_report_stair.xml',
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}