{
    "name": "Re-Generate Valuation & Entries",
    "summary": "Re-generate Stock Valuation Layers and related Journal Entries for selected products/date range/company",
    "description": """
    This module provides functionality to delete and re-create Stock Valuation Layers (SVL) 
    and related Journal Entries for selected products, date ranges, and companies. 
    It includes a wizard interface with dry-run capabilities, backup functionality, 
    and support for Landed Costs scenarios.
    """,
    "version": "17.0.1.0.0",
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