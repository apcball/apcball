# Copyright 2017 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "buz Sale Manual Delivery",
    "category": "Sale",
    "author": "Camptocamp SA, Odoo Community Association (OCA)",
    "license": "AGPL-3",
    "version": "17.0.1.0.0",
    "website": "https://github.com/OCA/sale-workflow",
    "summary": "Create manually your deliveries",
    "depends": ["base", "sale", "stock_delivery", "sale_stock", "sales_team"],
    "data": [
        "security/manual_delivery_security.xml",
        "security/ir.model.access.csv",
        "views/crm_team.xml",
        "views/sale_order.xml",
        "wizard/manual_delivery.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "pre_init_hook": "pre_init_hook",
}
