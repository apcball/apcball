{
    'name': 'Purchase Bill Bypass Control Policy',
    'version': '17.0.1.0.0',
    'category': 'Inventory/Purchase',
    'summary': 'Allows authorized users to bypass standard control policy and bill products before receipt.',
    'description': """
        Standard Odoo Purchase Orders with Control Policy = Received quantities only allow Vendor Bills to be created after products are received.
        This module allows authorized users to create Vendor Bills even when goods have not yet been received.
    """,
    'author': 'Antigravity',
    'depends': ['purchase'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'wizard/bill_bypass_confirm_views.xml',
        'views/res_partner_views.xml',
        'views/purchase_order_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
