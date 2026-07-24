{
    "name": "Mogen Smart S&OP Supply",
    "summary": "Supply projections and S&OP recommendations",
    "version": "17.0.1.0.0",
    "category": "Operations/Planning",
    "author": "Mogen Co., Ltd.",
    "license": "LGPL-3",
    "depends": ["mogen_sop_core", "mogen_sop_demand", "stock", "purchase", "mrp"],
    "data": [
        "security/supply_security.xml",
        "security/ir.model.access.csv",
        "views/supply_plan_views.xml",
        "views/supply_menu.xml",
    ],
    "application": False,
    "installable": True,
}
