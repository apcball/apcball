{
    "name": "Re-Generate Valuation & Entries",
    "summary": "Re-generate Stock Valuation Layers and related Journal Entries for selected products/date range/company/location",
    "description": """
    This module provides functionality to delete and re-create Stock Valuation Layers (SVL) 
    and related Journal Entries for selected products, date ranges, companies, and locations. 
    It includes a wizard interface with dry-run capabilities, backup functionality, 
    and support for Landed Costs scenarios.
    
    This module is compatible with stock_valuation_layer_usage module and will properly
    handle usage tracking during regeneration.
    
    Features:
    - Filter by products, categories, or custom domain
    - Filter by date range
    - Filter by company
    - Filter by stock locations (new in v1.1.0)
    - Auto-detect products with valuation issues in selected locations (new in v1.2.0)
    - Detect negative valuation issues (new in v1.4.0)
    - Detect back-date issues (date mismatch, order mismatch, FIFO sequence) (new in v1.4.0)
    - Prevent re-detection of recently processed products (new in v1.4.0)
    - Clear selection button for easy restart (new in v1.4.0)
    - Dry-run mode for preview
    - Backup and restore functionality
    - Support for FIFO and AVCO costing methods
    - Support for Landed Costs
    - Compatible with stock_valuation_layer_usage module (new in v1.3.0)
    """,
    "version": "17.0.1.4.1",
    'author': 'apcball',
    "category": "Inventory/Inventory",
    "license": "LGPL-3",
    "depends": [
        "stock",
        "account", 
        "stock_landed_costs",
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        
        'data/menu.xml',
        'data/server_actions.xml',
        
        'views/product_views.xml',
        'views/wizard_views.xml',
        'views/rollback_wizard_views.xml',
        'views/log_views.xml',
        'views/menus.xml',
        
        'report/templates.xml',
    ],
    "demo": [
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "maintainers": ["Your Name"],
    "website": "https://www.yourcompany.com",
}