# -*- coding: utf-8 -*-
{
    'name': 'Marketplace Stock Management',
    'version': '17.0.1.0.1',
    'category': 'Inventory/Warehouse',
    'summary': 'Manage Shopee and Lazada marketplace stock synchronization',
    'description': """
Marketplace Stock Management
=============================
* Integrate with Shopee and Lazada marketplaces
* Sync product stock bidirectionally
* Manage buffer stock locations for marketplace fulfillment
* Import marketplace orders and create Odoo sales orders
* API logging and stock history tracking
    """,
    'author': 'Buz',
    'website': 'https://www.buz.co.th',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'sale',
        'stock',
        'product',
        'mail',
        'contacts',
        'uom',
    ],
    'data': [
        # Security
        'security/security.xml',
        'security/ir.model.access.csv',
        
        # Data
        'data/stock_location_data.xml',
        'data/ir_cron_data.xml',
        
        # Views
        'views/marketplace_account_views.xml',
        'views/marketplace_api_log_views.xml',
        'views/marketplace_stock_history_views.xml',
        'views/marketplace_product_views.xml',
        'views/marketplace_order_views.xml',
        'views/product_template_views.xml',
        'views/product_product_views.xml',
        'views/menu_views.xml',
        
        # Wizards
        'wizards/transfer_to_buffer_wizard_views.xml',
        'wizards/fetch_stock_wizard_views.xml',
        'wizards/refill_stock_wizard_views.xml',
        'wizards/fetch_orders_wizard_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
