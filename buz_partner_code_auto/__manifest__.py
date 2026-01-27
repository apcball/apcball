{
    'name': 'Partner Code Auto-fill',
    'version': '17.0.1.0.0',
    'category': 'Sales/Purchase',
    'summary': 'Auto-fill partner details using partner code in SO and PO',
    'description': """
        This module adds partner code field in SO and PO forms.
        When user enters partner code, it automatically fills the partner details.
    """,
    'depends': ['base', 'sale_management', 'purchase', 'account'],
    'data': [
        'security/ir.model.access.csv',
        'views/res_partner_views.xml',
        'views/sale_order_views.xml',
        'views/purchase_order_views.xml',
        'views/account_move_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}