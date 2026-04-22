# -*- coding: utf-8 -*-
# File: __manifest__.py
# Purpose: Module manifest for stock_enhanced_checker

{
    'name': 'Stock Enhanced Checker',
    'version': '17.0.1.0.0',
    'summary': 'Advanced stock checker with OWL UI, location filters, and quotation creation',
    'description': """
        Stock Enhanced Checker provides a modern OWL-based dashboard to:
        - View real available stock (on hand minus reserved) per warehouse/location
        - See incoming stock from confirmed Purchase Orders
        - Multi-select products and create Sale Quotations directly
        - Filter by stock status with configurable low-stock threshold
    """,
    'category': 'Inventory',
    'author': 'Custom',
    'license': 'LGPL-3',
    'depends': ['stock', 'sale_management', 'product', 'web', 'purchase', 'buz_partner_code_auto'],
    'data': [
        'security/ir.model.access.csv',
        'views/stock_checker_menu.xml',
        'views/res_config_settings_view.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'stock_enhanced_checker/static/src/css/stock_checker.css',
            'stock_enhanced_checker/static/src/xml/stock_checker_action.xml',
            'stock_enhanced_checker/static/src/xml/stock_checker_table.xml',
            'stock_enhanced_checker/static/src/js/stock_checker_filters.js',
            'stock_enhanced_checker/static/src/js/stock_checker_table.js',
            'stock_enhanced_checker/static/src/js/stock_checker_action.js',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
