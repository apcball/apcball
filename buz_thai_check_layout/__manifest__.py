{
    'name': 'buz Thai Check Layout',
    'version': '17.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Thai Check Printing Layout',
    'depends': ['account'],
    'data': [
        'security/ir.model.access.csv',
        'data/account_check_layout.xml',
        'report/print_check.xml',
    ],
    'assets': {
        'web.report_assets_common': [
            '/buz_thai_check_layout/static/fonts/Sarabun-Regular.ttf',
            '/buz_thai_check_layout/static/src/scss/style.scss',
        ],
    },
    'license': 'LGPL-3',
}