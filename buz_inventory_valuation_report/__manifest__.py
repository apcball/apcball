# -*- coding: utf-8 -*-
{
    'name': 'BUZ Inventory Valuation Report (Excel)',
    'version': '17.0.1.0.0',
    'category': 'Warehouse',
    'summary': 'Product Inventory Valuation Filter by Date Report with XLS export',
    'description': """
        This module allows users to generate inventory valuation reports 
        based on stock movements within a specified date range.
        Reports can be exported in XLS format.
        
        Features:
        - Calculate inventory valuation based on actual stock movements
        - Filter by date range (shows stock position as of end date)
        - Filter by warehouse and location
        - Filter by specific products and product categories
        - Export reports in XLS format
        - Professional report layout
        - Accurate cost calculation based on move history
        
        Note: PDF reports have been removed - only Excel format is supported.
        The report shows inventory balance calculated from all stock movements up to the selected end date.
    """,
    'author': 'apcball',
    'website': 'https://www.buzsolutions.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'stock',
        'stock_account',
        'product',
        'report_xlsx',
    ],
    'data': [
        'security/ir.model.access.csv',
        'wizard/inventory_valuation_wizard_views.xml',
        'views/inventory_valuation_report_views.xml',
    ],
    'demo': [],
    'installable': True,
    'auto_install': False,
    'application': False,
}
