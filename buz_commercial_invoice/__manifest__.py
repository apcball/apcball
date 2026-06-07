{
    'name': 'Custom Commercial Invoice Report',
    'version': '17.0.1.0.1',
    'category': 'Accounting',
    'summary': 'Customize Commercial Invoice Report',
    'description': """
        Customization for Commercial Invoice Report in Accounting module.
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'depends': [
        'base',
        'account',
        'stock',
        'sale',
        'mrp',
        'buz_product_dimension',
        'buzcustom_product_name_eng',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'report/paperformat.xml',
        'report/report_action.xml',
        'report/packing_list_report.xml',
        'report/commercial_invoice_sale_order_report.xml',
        'views/account_move_view.xml',
        'views/stock_picking_view.xml',
        'views/sale_order_view.xml',
    ],
    'assets': {
        'web.assets_backend': [
            # Add your CSS/JS files if needed
        ],
    },
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
    'auto_install': False,
}