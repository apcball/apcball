{
    'name': 'Buz Custom Partner',
    'version': '17.0.2.3',
    'category': 'Customers',
    'summary': 'Add Partner Code and Additional Fields to res.partner',
    'description': """
Custom Partner Module for Odoo 17
==================================

This module adds:
- Auto-generated partner codes (C for customers, V for vendors)
- Old partner code field
- Office field
- Partner group field
- Partner type field

Features:
- Automatic sequence generation for customer and vendor codes
- Unique constraint on partner codes
- Integration with existing partner form view
    """,
    'author': 'Your Name',
    'depends': ['base', 'contacts', 'account', 'purchase', 'sale'],
    'data': [
        'security/ir.model.access.csv',
        'views/res_partner_views.xml',
        'views/res_partner_config_views.xml',
        'views/purchase_order_views.xml',
        'views/sale_order_views.xml',
        'data/sequence.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}