{
    'name': 'buz Multiple Discounts on Sale and Invoice',
    'version': '17.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Apply multiple discounts on sale orders and invoices',
    'description': """
Multiple Discounts
=================
This module allows to apply multiple discounts on sale order lines and invoice lines.
You can add multiple discount amounts separated by '+'.
For example, if you apply '10+5+2', it will:
- First apply 10% discount
- Then apply 5% on the new amount
- Finally apply 2% on the resulting amount
    """,
    'author': 'Odoo Community Association (OCA)',
    'website': 'https://github.com/OCA/sale-workflow',
    'depends': [
        'sale_management',
        'account',
    ],
    'data': [
        'views/sale_order_views.xml',
        'views/account_move_views.xml',
        'report/sale_report_templates.xml',
        'report/account_report_templates.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'multi_discounts/static/src/js/**/*',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}