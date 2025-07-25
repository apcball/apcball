# Copyright (C) 2020, Brian McMaster
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "buz Field Service - Stock Equipment",
    "summary": "Integrate stock operations with your field service equipments",
    "version": "17.0.1.11.0",
    "category": "Field Service",
    "author": "Open Source Integrators, "
    "Brian McMaster, "
    "Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/field-service",
    "depends": [
        "fieldservice_stock",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/fsm_equipment.xml",
        "views/product_template.xml",
        "views/stock_picking_type.xml",
        "views/stock_lot.xml",
        "views/menu.xml",
    ],
    "license": "AGPL-3",
    "development_status": "Beta",
    "maintainers": [
        "brian10048",
        "wolfhall",
        "max3903",
        "smangukiya",
    ],
}
