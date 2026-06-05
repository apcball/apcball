{
    "name": "Sale Target Management",
    "version": "17.0.1.0.0",
    "summary": "Separate My Target and Team Target management with multi-team support.",
    "description": """
        Sale Target Management
        ======================

        Features:
        - My Target: Set targets for individual salespersons (user only)
        - Team Target: Set targets for sales teams (supports multiple teams)
        - Multiple target points: Sale Order Confirm, Invoice Validation, Invoice Paid
        - Real-time achievement tracking with theoretical calculations
        - Email notifications for target confirmation and closure
        - Access rights: Users see only their targets, Managers see all
    """,
    "category": "Sales",
    "author": "Your Company",
    "website": "https://yourcompany.com",
    "depends": ["sale_management", "crm", "account"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/email_templates.xml",
        "views/my_target_views.xml",
        "views/team_target_views.xml",
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "sale_target/static/src/css/target.css",
        ],
    },
    "installable": True,
    "application": True,
    "auto_install": False,
    "license": "LGPL-3",
}
