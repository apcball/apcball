{
    "name": "Sales Reservation Management",
    "version": "17.0.1.0.0",
    "category": "Inventory/Reservations",
    "summary": "Advanced sales reservation management with VIP allocation, expiration, and approval workflows",
    "description": """
Sales Reservation Management
============================
Enterprise-grade stock reservation system for sales orders.

Key Features:
- Customer-specific product reservations
- VIP customer stock allocation
- Reservation expiration with auto-release
- Multi-step approval workflow for shortages
- Real-time available-to-promise calculations
- Reservation dashboard with KPIs and charts
- Comprehensive reservation reports
- Multi-company and multi-warehouse compatible
- Reservation release wizard with reason tracking
""",
    "author": "Your Company",
    "website": "https://www.yourcompany.com",
    "depends": [
        "sale",
        "stock",
        "product",
        "mail",
        "uom",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/sequence.xml",
        "data/cron_data.xml",
        "data/mail_template.xml",
        "views/stock_reservation_views.xml",
        "views/product_views.xml",
        "views/sale_order_views.xml",
        "report/reservation_report_views.xml",
        "views/menu_views.xml",
        "wizard/reservation_release_wizard_views.xml",
        "report/reservation_report_templates.xml",
    ],
    "demo": [
        "data/demo.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
    "license": "LGPL-3",
    "images": ["static/description/banner.png"],
}
