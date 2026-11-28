{
    "name": "Sales Dashboard (SO + POS)",
    "version": "17.0.1.4.0",
    "summary": "Sales dashboard for the sales team: quotations, sale orders, delivery "
               "and POS invoices, with personal saved filters and Excel export",
    "category": "Sales",
    "author": "Mogen Co., Ltd.",
    "website": "https://mogen.co.th",
    "license": "LGPL-3",
    "depends": ["sale_management", "sale_stock", "sales_team", "account", "product",
                "pos_lite"],
    "external_dependencies": {"python": ["openpyxl", "xlsxwriter"]},
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/report_views.xml",
        "views/product_views.xml",
        "views/target_views.xml",
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "buz_sales_dashboard/static/src/dashboard/*",
        ],
    },
    "post_init_hook": "post_init_hook",
    "application": True,
    "installable": True,
}
