{
    "name": "Mogen Smart S&OP Optimization",
    "summary": "Inventory and capacity optimization foundation for Smart S&OP",
    "version": "17.0.1.0.0",
    "category": "Operations/Planning",
    "author": "Mogen Co., Ltd.",
    "license": "LGPL-3",
    "depends": ["mogen_sop_forecast", "mogen_sop_scenario", "mogen_sop_inventory", "mogen_sop_supply", "mogen_sop_production", "purchase", "mrp", "stock"],
    "data": [
        "security/optimization_security.xml",
        "security/ir.model.access.csv",
        "data/optimization_data.xml",
        "views/optimization_views.xml",
        "views/optimization_menu.xml",
    ],
    "application": False,
    "installable": True,
}
