{
    "name": "Biz Web List Column Order",
    "version": "17.0.1.1.0",
    "author": "Custom",
    "license": "LGPL-3",
    "category": "Web",
    "summary": "Drag list-view column headers to reorder them; order is remembered per user.",
    "depends": ["web"],
    "assets": {
        "web.assets_backend": [
            "biz_web_list_column_order/static/src/js/list_column_order.js",
            "biz_web_list_column_order/static/src/js/list_column_order.scss",
            "biz_web_list_column_order/static/src/xml/list_column_order.xml",
        ],
    },
    "installable": True,
    "application": False,
}
