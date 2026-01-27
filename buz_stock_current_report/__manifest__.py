{
    'name': 'Current Stock Report',
    'version': '17.0.1.0.0',
    'summary': 'View and Export Current Stock by Location and Date with Enhanced UI',
    'category': 'Inventory/Reports',
    'depends': ['stock', 'report_xlsx'],
    'data': [
        'security/stock_current_report_security.xml',
        'views/stock_current_report_views.xml',
        'views/stock_current_report_sidebar_views.xml',
        'views/stock_current_export_wizard_views.xml',
        # transfer wizard view removed as transfer feature disabled
    ],
    'assets': {
        'web.assets_backend': [
            'buz_stock_current_report/static/src/css/stock_current_report.css',
            'buz_stock_current_report/static/src/js/stock_current_report.js',
            'buz_stock_current_report/static/src/xml/stock_current_report.xml',
        ],
    },
    'installable': True,
    'application': False,
}