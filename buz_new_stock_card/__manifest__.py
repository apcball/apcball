{
    "name": "Interactive Stock Card",
    "version": "17.0.1.0.0",
    "category": "Inventory/Reports",
    "summary": "Interactive Owl-based stock card report with location tree drill-down",
    "author": "Mogen Co., Ltd.",
    "license": "LGPL-3",
    "depends": [
        "stock",
        "product",
        "web",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/stock_card_menu.xml",
        "report/stock_card_report_actions.xml",
        "report/stock_card_report_template.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "buz_new_stock_card/static/src/components/**/*.js",
            "buz_new_stock_card/static/src/components/**/*.xml",
            "buz_new_stock_card/static/src/scss/*.scss",
        ],
    },
    "installable": True,
    "application": False,
}
