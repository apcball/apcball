# Copyright (C) 2021 - TODAY, Open Source Integrators
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "buz Field Service - Repair",
    "summary": "Integrate Field Service orders with MRP repair orders",
    "version": "17.0.1.11.0",
    "category": "Field Service",
    "author": "Open Source Integrators, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/field-service",
    "depends": [
        "fieldservice_equipment_stock",
        "repair",
    ],
    "data": ["data/fsm_order_type.xml", "views/fsm_order_view.xml"],
    "license": "AGPL-3",
    "development_status": "Beta",
    "maintainers": [
        "smangukiya",
        "max3903",
    ],
    "installable": True,
}
