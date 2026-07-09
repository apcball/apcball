{
    'name': 'POS Lite',
    'version': '17.0.3.7.0',
    'category': 'Sales',
    'summary': 'Lightweight form-based order entry for phone, LINE, and walk-in orders',
    'description': """
POS Lite
========
Simple form-based order entry for phone, LINE, walk-in, and other manual orders.
Creates invoice, stock picking, and printable receipt from a lightweight backend form.

Features:
- Process & post invoice in one click
- Hold/resume orders
- Daily session tracking & close
- Optional internal records for manual/refund flows
- Return & exchange support
- Multi-size receipt (58mm, 80mm, A4)
- Sales analytics (pivot, graph)
- Multi-company support
- Sales margin from Standard Cost Pricelist (matches SO)
    """,
    'author': 'AI-DEV-Module-Odoo17',
    'website': 'https://github.com/apcball/AI-DEV-Module-Odoo17',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'contacts',
        'product',
        'stock',
        'account',
        'sale_management',
        'hr',
        'buz_custom_invoice',
        'buz_sale_pricelist_standard_cost',
        'marketplace_settlement',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequence_data.xml',
        'data/migration_fix_return_session.xml',
        'report/receipt_report.xml',
        'report/pos_receipt_report.xml',
        'views/pos_order_view.xml',
        'views/pos_config_view.xml',
        'views/pos_session_view.xml',
        'views/report_views.xml',
        'views/menu.xml',
        'views/pos_lite_terminal.xml',
        'views/product_product_view.xml',
        'wizard/return_wizard_view.xml',
        'wizard/start_sale_wizard_view.xml',
    ],
    'assets': {
        'web.report_assets_common': [
            '/pos_lite/static/fonts/Sarabun-Regular.ttf',
            '/pos_lite/static/fonts/Sarabun-Bold.ttf',
            '/pos_lite/static/fonts/Sarabun-Italic.ttf',
            '/pos_lite/static/fonts/Sarabun-BoldItalic.ttf',
        ],
    },
    'application': True,
    'installable': True,
    'auto_install': False,
}
