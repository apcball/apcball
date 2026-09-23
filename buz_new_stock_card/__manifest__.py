{
    "name": "Interactive Stock Card",
    "version": "17.0.1.4.0",
    "category": "Inventory/Reports",
    "summary": "Interactive Owl-based stock card report with location tree drill-down",
    "author": "Mogen Co., Ltd.",
    "license": "LGPL-3",
    "depends": [
        "stock",
        "stock_account",
        "stock_by_locations",
        "stock_valuation_location",
        "stock_fifo_by_location",
        "product",
        "web",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/stock_card_menu.xml",
        "wizard/stock_card_export_wizard_view.xml",
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
