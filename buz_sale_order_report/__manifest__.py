{
    'name': 'Custom Sale Order Report',
    'version': '17.0.1.0.0',
    'category': 'Sales',
    'summary': 'Custom Sale Order Report with Thai and English versions',
    'description': """
        Custom Sale Order Report Module
        - Thai and English versions
        - Customized layout matching the provided template
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'depends': ['sale'],
    'data': [
        'security/ir.model.access.csv',
        'data/paper_format.xml',
        'reports/sale_order_report_en.xml',
        'reports/sale_order_report_th.xml',
        'reports/sale_order_report_action.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}