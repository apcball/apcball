{
    'name': 'BUZ Custom Purchase Order',
    'version': '17.0.1.0.0',
    'category': 'Purchase',
    'summary': 'Custom Purchase Order with Approval Workflow and Reports',
    'description': """
        Custom module for purchase order management:
        - Two level approval process based on amount
        - Level 1 approval for amount <= 50000
        - Level 2 approval for amount > 50000
        - Custom PDF reports with discount calculation
        - Multi-language support (Thai/English)
    """,
    'depends': ['base', 'purchase', 'mail'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/mail_template.xml',
        'views/purchase_view.xml',
        'views/reject_wizard_view.xml',
        'reports/purchase_order_report.xml',
        'reports/purchase_order_report_eng.xml',
        'reports/purchase_order_test.xml',
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