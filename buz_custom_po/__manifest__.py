{
    'name': 'BUZ Custom Purchase Order',
    'version': '17.0.3.0.0',
    'category': 'Purchase',
    'summary': 'Custom Purchase Order with Enhanced Features and Reports',
    'description': """
        Custom module for purchase order management:
        - Enhanced purchase order forms with additional fields
        - Custom PDF reports with discount calculation
        - Multi-language support (Thai/English)
        - Thai text conversion for amounts
        - VAT detection functionality
    """,
    'depends': ['base', 'purchase', 'mail', 'hr'],
    'data': [
        'data/mail_template.xml',
        'views/purchase_view.xml',
        'reports/purchase_order_report.xml',
        'reports/purchase_order_report_eng.xml',
        'reports/purchase_order_test.xml',
        'reports/purchase_agreements_report.xml',
        'views/report_menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'buz_custom_po/static/src/scss/style.scss',
        ],
        'web.report_assets_common': [
            'buz_custom_po/static/src/scss/style.scss',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}