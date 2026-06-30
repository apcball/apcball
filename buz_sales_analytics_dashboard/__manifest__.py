{
    "name": "Sales Analytics Dashboard",
    "version": "17.0.1.1.0",
    "summary": "Advanced sales analytics dashboard with KPIs, charts, funnel, and forecast",
    "category": "Sales",
    "author": "Mogen Co., Ltd.",
    "website": "https://mogen.co.th",
    "depends": [
        "sale_management",
        "crm",
        "account",
        "sales_team",
        "pos_lite",
        "stock",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/cron_data.xml",
        "views/dashboard_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "buz_sales_analytics_dashboard/static/src/scss/dashboard.scss",
            "buz_sales_analytics_dashboard/static/src/js/dashboard.js",
            "buz_sales_analytics_dashboard/static/src/xml/dashboard.xml",
        ],
    },
    "installable": True,
    "application": True,
    "auto_install": False,
    "license": "LGPL-3",
}
