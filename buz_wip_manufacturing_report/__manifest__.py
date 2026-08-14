{
    "name": "WIP Manufacturing Report",
    "version": "17.0.1.0.0",
    "category": "Manufacturing/Reports",
    "summary": "Read-only WIP material consumption report by Manufacturing Order",
    "author": "Mogen Co., Ltd.",
    "license": "LGPL-3",
    "depends": [
        "mrp",
        "stock",
        "product",
        "web",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "wizard/wip_manufacturing_export_wizard_views.xml",
        "views/wip_manufacturing_menu.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "buz_wip_manufacturing_report/static/src/components/**/*.js",
            "buz_wip_manufacturing_report/static/src/components/**/*.xml",
            "buz_wip_manufacturing_report/static/src/scss/*.scss",
        ],
    },
    "installable": True,
    "application": False,
}
