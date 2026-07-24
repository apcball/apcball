{
    "name": "Mogen Smart S&OP Core",
    "summary": "Shared planning cycles, security, and navigation for Smart S&OP",
    "version": "17.0.1.0.0",
    "category": "Operations/Planning",
    "author": "Mogen Co., Ltd.",
    "license": "LGPL-3",
    "depends": ["base", "mail", "product", "stock", "purchase", "mrp"],
    "data": [
        "security/sop_security.xml",
        "security/ir.model.access.csv",
        "data/sop_sequence.xml",
        "views/sop_views.xml",
        "views/sop_menu.xml",
    ],
    "demo": [
        "demo/sop_demo.xml",
    ],
    "application": True,
    "installable": True,
}
