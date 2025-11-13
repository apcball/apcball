# Part of Odoo. See COPYRIGHT & LICENSE files for full copyright and licensing details.
{
    'name': 'Stock By Location',
    'version': '17.0.0.0.0',
    'author': 'Techultra Solutions Private Limited',
    'website': "https://www.techultrasolutions.com/",
    'category': 'Inventory',
    'summary': """
        Track product stock and costs based on specific warehouse locations
        stock
        inventory
        location
        cost tracking
        warehouse
        cost
        multi-location
        multi-warehouse
        stock report
        location-wise stock
        inventory control
        tus
        techultra
        techultra_private_limited_solution
        Odoo Stock By Location
        Odoo Inventory By Location
        Odoo Warehouse Stock Tracking
        Odoo Stock Location Management
        Odoo Multi-Warehouse Inventory
        Odoo Product Stock by Warehouse
        Odoo Location-Wise Inventory
        Odoo Stock Analysis by Location
        Odoo Inventory Cost by Location
        Odoo Location-Based Stock Management
        Odoo Inventory by Warehouse Location
        Odoo Stock Management by Location
        Odoo Location-Based Inventory Tracking
        Odoo Warehouse Stock Visibility
        Odoo Inventory Cost by Location'
        Odoo Multi-Warehouse Stock Control
        Track Product Stock Per Location in Odoo
        Odoo Inventory Reporting by Location
        Odoo Stock Levels by Warehouse
        Odoo Real-Time Stock per Location
        Track Inventory by Location in Odoo
        Manage Warehouse Stock Separately in Odoo
        Odoo Module for Stock Per Location
        Odoo Real-Time Inventory by Warehouse
        Odoo Custom Stock Report by Location
        Monitor Stock Level by Warehouse in Odoo
        Odoo Inventory Module for Multi-Location Tracking
        Odoo Landed Cost by Location Integration 
        Odoo Advanced Inventory Location Features
        Odoo Stock Cost History per Location
    """,
    'description': """
         Stock By Location
        =================
        This module allows you to manage and monitor inventory stock levels and costs 
        per location or warehouse in Odoo.

        Key Features:
        - Enhanced stock visibility per location
        - Historical cost tracking by location
        - Integration with landed costs and accounting
        - Extended views on warehouse, product, and location forms

        Suitable for companies needing precise location-based inventory costing and reporting.
         stock
        inventory
        location
        cost tracking
        warehouse
        cost
        multi-location
        multi-warehouse
        stock report
        location-wise stock
        inventory control
        tus
        techultra
        techultra_private_limited_solution
        Odoo Stock By Location
        Odoo Inventory By Location
        Odoo Warehouse Stock Tracking
        Odoo Stock Location Management
        Odoo Multi-Warehouse Inventory
        Odoo Product Stock by Warehouse
        Odoo Location-Wise Inventory
        Odoo Stock Analysis by Location
        Odoo Inventory Cost by Location
        Odoo Location-Based Stock Management
        Odoo Inventory by Warehouse Location
        Odoo Stock Management by Location
        Odoo Location-Based Inventory Tracking
        Odoo Warehouse Stock Visibility
        Odoo Inventory Cost by Location'
        Odoo Multi-Warehouse Stock Control
        Track Product Stock Per Location in Odoo
        Odoo Inventory Reporting by Location
        Odoo Stock Levels by Warehouse
        Odoo Real-Time Stock per Location
        Track Inventory by Location in Odoo
        Manage Warehouse Stock Separately in Odoo
        Odoo Module for Stock Per Location
        Odoo Real-Time Inventory by Warehouse
        Odoo Custom Stock Report by Location
        Monitor Stock Level by Warehouse in Odoo
        Odoo Inventory Module for Multi-Location Tracking
        Odoo Landed Cost by Location Integration 
        Odoo Advanced Inventory Location Features
        Odoo Stock Cost History per Location

    """,
    'depends': ['sale_management', 'stock_landed_costs' ,'stock_account', 'sale', 'sale_stock', 'purchase'],
    'data': [
        'security/ir.model.access.csv',
        'views/sale_order.xml',
        'views/stock_warehouse_view.xml',
        'views/product_view.xml',
        'views/stock_location.xml',
        'views/product_cost_location_history.xml',
    ],
    "images": [
        "static/description/main_screen.gif",
    ],
    'price': 23.00,
    'currency': 'EUR',
    'installable': True,
    'auto_install': False,
    'license': 'OPL-1',
}
