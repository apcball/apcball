{
    "name": "BUZ Sales Performance Engine",
    "version": "17.0.2.0.0",
    "summary": "Measure REAL sales performance: recognized only when delivered AND invoice posted. Includes POS Lite sales.",
    "description": """
BUZ Sales Performance Engine
===========================

Recognizes sales ONLY when all business conditions are satisfied:
  * Sale Order confirmed (sale)
  * Delivery done (stock.picking)
  * Customer invoice posted (account.move)

Partial delivery, partial invoicing, returns and credit notes are handled
automatically at the sale-order-line granularity via a summary table
``buz.sales.performance.result`` that the dashboard reads exclusively.

Features
--------
* Salesperson / Sales Team / Company targets (daily, monthly, quarterly, yearly)
* Real-time OWL dashboard (Chart.js, no extra JS dependency)
* KPI cards, sales-vs-target, delivery / invoice / refund trends,
  top customers / products / salespersons / teams, leaderboards
* Drill-downs to invoices, deliveries, sale orders, credit notes
* Event-driven incremental recompute + nightly safety-net cron
* Multi-company, multi-currency
* 3-tier security: own records / own team / all
""",
    "category": "Sales",
    "author": "Mogen Co., Ltd.",
    "website": "https://mogen.co.th",
    "license": "LGPL-3",
    "depends": [
        "sale_management",
        "sale_stock",
        "account",
        "crm",
        "pos_lite",
    ],
    "data": [
        "security/ir_module_category_data.xml",
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/spe_sequence.xml",
        "data/email_templates.xml",
        "data/cron_data.xml",
        "wizard/spe_recompute_wizard_views.xml",
        "views/sale_performance_result_views.xml",
        "views/sale_performance_target_views.xml",
        "views/sale_order_views.xml",
        "views/crm_team_views.xml",
        "views/res_users_views.xml",
        "views/spe_dashboard_views.xml",
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "buz_sales_performance_engine/static/src/scss/spe_dashboard.scss",
            "buz_sales_performance_engine/static/src/xml/spe_dashboard.xml",
            "buz_sales_performance_engine/static/src/js/spe_dashboard.js",
        ],
    },
    "installable": True,
    "application": True,
    "auto_install": False,
}
