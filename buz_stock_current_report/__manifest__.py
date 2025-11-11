{
    'name': 'Current Stock Report by Date',
    'version': '17.0.1.0.0',
    'summary': 'View and Export Current Stock by Location and Date',
    'category': 'Inventory/Reports',
    'depends': ['stock', 'report_xlsx'],
    'data': [
        'security/stock_current_report_security.xml',
        'views/stock_current_report_views.xml',
        'views/stock_current_export_wizard_views.xml',
    ],
    'installable': True,
    'application': False,
}