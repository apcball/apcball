{
    "name": "buz Sales Target Management",
    "version": "17.0.1.2.0",
    "summary": "Sales target management for salespersons and teams with advanced features.",
    "description": """
        Sales Target Management
        =======================
        
        This module provides comprehensive sales target management features:
        
        Features:
        - Set sales targets for individual salespersons or teams
        - Multiple target points: Sale Order Confirm, Invoice Validation, Invoice Paid, POS Lite Sale
        - Theoretical achievement calculation
        - Email notifications for target confirmation and closure
        - Multi-currency support
        - Access rights: Salespersons can see only their targets, Managers see all
        - Validation to prevent duplicate targets for same person/team
        - Real-time achievement tracking
    """,
    "category": "Sales",
    "author": "Mogen Co., Ltd.",
    "website": "https://mogen.co.th",
    "depends": ["sale_management", "crm", "account", "pos_lite"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/email_templates.xml",
        "data/cron_data.xml",
        "views/sales_target_views.xml",
        "views/my_target_dashboard.xml",
        "views/crm_team_dashboard.xml",
        "views/sales_target_menu.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "sales_target_custom/static/src/scss/dashboard.scss",
        ],
    },
    "installable": True,
    "application": True,
    "auto_install": False,
    "license": "LGPL-3"
}
