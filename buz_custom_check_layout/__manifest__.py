{
    'name': 'BUZ Custom Check Layout',
    'version': '1.0',
    'category': 'Accounting',
    'summary': 'Custom Check Layout for BUZ',
    'description': """
        Custom Check Layout Module for BUZ
        - Customized check layout
        - Thai baht text conversion
        - Preview function
    """,
    'depends': ['base', 'account', 'account_check_printing'],
    'data': [
        'security/ir.model.access.csv',
        'data/check_layout.xml',
        'report/print_check.xml',
        'views/account_payment_views.xml',
    ],
    'assets': {
        'web.report_assets_common': [
            '/buz_custom_check_layout/static/fonts/Sarabun-Regular.ttf',
            '/buz_custom_check_layout/static/src/scss/style.scss',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}