# Copyright 2018 Acsone
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "buz Sale Blanket Orders",
    "category": "Sale",
    "license": "AGPL-3",
    "author": "Acsone SA/NV, Odoo Community Association (OCA)",
    "version": "17.0.1.1.0",
    "website": "https://github.com/OCA/sale-workflow",
    "summary": "Blanket Orders",
    "depends": ["uom", "sale_management"],
    "data": [
        "security/groups.xml",
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/sequence.xml",
        "data/ir_cron.xml",
        "wizard/create_sale_orders.xml",
        "views/sale_config_settings.xml",
        "views/sale_blanket_order_views.xml",
        "views/sale_blanket_order_line_views.xml",
        "views/sale_order_views.xml",
        "report/templates.xml",
        "report/report.xml",
    ],
    "installable": True,
}
