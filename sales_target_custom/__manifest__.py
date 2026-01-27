{
    "name": "buz Sales Target Management",
    "version": "17.0.1.0.0",
    "summary": "Sales target management for salespersons and teams with advanced features.",
    "description": """
        Sales Target Management
        =======================
        
        This module provides comprehensive sales target management features:
        
        Features:
        - Set sales targets for individual salespersons or teams
        - Multiple target points: Sale Order Confirm, Invoice Validation, Invoice Paid
        - Theoretical achievement calculation
        - Email notifications for target confirmation and closure
        - Multi-currency support
        - Access rights: Salespersons can see only their targets, Managers see all
        - Validation to prevent duplicate targets for same person/team
        - Real-time achievement tracking
    """,
    "category": "Sales",
    "author": "Your Company",
    "website": "https://yourcompany.com",
    "depends": ["sale_management", "crm", "account"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/email_templates.xml",
        "views/sales_target_views.xml",
        "views/sales_target_menu.xml",
        "views/sales_target_dashboard_new.xml"
    ],
    "assets": {
        "web.assets_backend": [
            "sales_target_custom/static/src/css/dashboard.css",
            "sales_target_custom/static/src/js/gauge_chart.js",
        ],
    },
    "installable": True,
    "application": True,
    "auto_install": False,
    "license": "LGPL-3"
}
