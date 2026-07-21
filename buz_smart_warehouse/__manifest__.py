{
    "name": "Smart Warehouse Dashboard",
    "version": "17.0.1.0.0",
    "summary": "Smart warehouse operations dashboard with rack occupancy map, "
    "KPIs, rule-based recommendations, and alerts",
    "category": "Inventory",
    "author": "Mogen Co., Ltd.",
    "website": "https://mogen.co.th",
    "depends": [
        "stock",
        "purchase",
        "sale_stock",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/dashboard_views.xml",
        "views/stock_location_views.xml",
        "views/layout_element_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "buz_smart_warehouse/static/src/scss/dashboard.scss",
            "buz_smart_warehouse/static/src/js/layout_designer.js",
            "buz_smart_warehouse/static/src/js/warehouse3d.js",
            "buz_smart_warehouse/static/src/js/map2d.js",
            "buz_smart_warehouse/static/src/js/dashboard.js",
            "buz_smart_warehouse/static/src/xml/dashboard.xml",
            "buz_smart_warehouse/static/src/xml/layout_designer.xml",
            "buz_smart_warehouse/static/src/xml/map2d.xml",
        ],
    },
    "installable": True,
    "application": True,
    "auto_install": False,
    "license": "LGPL-3",
}
