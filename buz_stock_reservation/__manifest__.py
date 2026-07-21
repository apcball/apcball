{
    "name": "Product Reservation Management",
    "version": "17.0.1.0.0",
    "category": "Inventory/Reservations",
    "summary": "Stock reservations with expiry tracking, release workflow and dashboard",
    "description": """
Product Reservation Management
==============================
Soft stock reservations for customers and projects.

Features:
- RSV-numbered reservations with expiry dates
- Release (partial/full) with reason tracking
- Extend expiry workflow
- Auto-expiration cron with notifications
- Product availability after reservations
- OWL dashboard with KPIs and charts
- Reservation analysis reports (customer / product / expiry)
""",
    "author": "Mogen Co.",
    "website": "https://www.mogen.co.th",
    "license": "LGPL-3",
    "depends": [
        "sale_stock",
        "stock",
        "mail",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/ir_sequence.xml",
        "data/ir_cron.xml",
        "views/stock_reservation_views.xml",
        "views/release_reason_views.xml",
        "views/res_config_settings_views.xml",
        "wizard/release_wizard_views.xml",
        "wizard/extend_expiry_wizard_views.xml",
        "report/reservation_analysis_views.xml",
        "views/product_views.xml",
        "views/dashboard_views.xml",
        "views/menu_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "buz_stock_reservation/static/src/scss/dashboard.scss",
            "buz_stock_reservation/static/src/js/dashboard.js",
            "buz_stock_reservation/static/src/xml/dashboard.xml",
        ],
    },
    "installable": True,
    "application": True,
    "auto_install": False,
}
