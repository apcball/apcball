{
    'name': 'Pricelist Product Manager (All-in-One Module)',
    'version': '17.0.1.0.0',
    'category': 'Sales',
    'summary': 'Manage prices by Product, not by rule',
    'description': """
        Odoo 17 Pricelist Product Manager (All-in-One Module)
        
        This module provides a comprehensive solution for managing product prices in pricelists with a product-centric approach.
        
        Key Features:
        - Product-centric Pricelist Matrix View: View and edit prices for all products in a pricelist in a single matrix.
        - Fast Search & Filtering: Quickly find products by name, code, category, or pricelist rules.
        - Inline Price Editing: Edit prices directly in the list view with automatic rule creation/updates.
        - Installation Price Support: Add installation prices to pricelist items and sale order lines.
        - Excel Export: Export pricelist data to Excel with highlighting for missing or expired rules.
        - Excel Import with Preview: Import prices from Excel with validation, preview of changes, and batch processing.
        - Price History Tracking: Log all price changes for audit and tracking.
        - Safe & Production-Ready: Optimized for performance with batch operations, error handling, and security controls.
        - Integration with Sales Orders: Include installation prices in sale order lines with automatic price enforcement.
        
        Author: APCBALL
    """,
    'author': 'APCBALL',
    'depends': ['sale', 'product'],
    'data': [
        'security/groups.xml',
        'security/ir.model.access.csv',
        'views/pricelist_product_matrix_view.xml',
        'views/sale_order_line_view.xml',
        'views/export_wizard_view.xml',
        'views/import_wizard_view.xml',
        'views/preview_view.xml',
        'views/pricelist_price_history_view.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
