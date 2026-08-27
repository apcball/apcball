{
    "name": "Shopee Connector",
    "version": "17.0.2.0.0",
    "category": "Sales/Sales",
    "summary": "Sync Shopee stock (item + model SKU) and orders with Odoo, "
    "push Odoo stock back to Shopee",
    "description": """
Shopee Open Platform Connector
==============================
- Pull product stock from Shopee into Odoo (item-level and model/variant SKU),
  reference only.
- Pull orders from Shopee and create draft Sale Orders in Odoo.
- Push Odoo free-to-use stock back to Shopee (opt-in per shop + per product).
- OAuth-style shop authorization flow with auto token refresh.
- Scheduled sync via cron (stock pull / order pull / stock push / token refresh).

Not included: order status push-back (ship / cancel), webhook push events,
multi-shop routing.
    """,
    "author": "MOGEN",
    "license": "LGPL-3",
    "depends": ["sale_management", "stock"],
    "external_dependencies": {"python": ["requests"]},
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron_data.xml",
        "views/shopee_config_views.xml",
        "views/product_views.xml",
        "views/sale_order_views.xml",
        "views/shopee_menu.xml",
    ],
    "installable": True,
    "application": True,
}
