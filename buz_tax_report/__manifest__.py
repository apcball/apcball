# -*- coding: utf-8 -*-
{
    'name': 'Tax Report Excel',
    'version': '17.0.1.0.0',
    'summary': 'Generate tax reports in Excel format',
    'description': '''
        Module to generate tax reports similar to account_tax_report_excel with Tax ID enhancement
        
        Features:
        - Generate tax reports in Excel format
        - Support for both detailed and summary views
        - Filter by tax type (Sales/Purchase/All)
        - Date range filtering
        - Professional Excel formatting
        - Company-wise reporting
        - Partner Tax ID/VAT display in detailed reports
        - Configurable tax report templates
    ''',
    'category': 'Accounting',
    'author': 'apcball',
    'website': 'https://www.example.com',
    'depends': ['account', 'report_xlsx', 'l10n_th_account_tax'],
    'data': [
        'security/ir.model.access.csv',
        'views/tax_report_wizard_view.xml',
        'views/tax_report_config_view.xml',
        'views/tax_report_actions.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
