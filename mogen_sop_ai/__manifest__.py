{
    "name": "Mogen Smart S&OP AI",
    "summary": "Auditable external AI gateway foundation for Smart S&OP",
    "version": "17.0.1.0.0",
    "category": "Operations/Planning",
    "author": "Mogen Co., Ltd.",
    "license": "LGPL-3",
    "depends": ["mogen_sop_core", "mogen_sop_scenario", "mogen_sop_risk", "mogen_sop_dashboard", "mail", "web"],
    "data": [
        "security/ai_security.xml",
        "security/ir.model.access.csv",
        "data/ai_data.xml",
        "views/ai_views.xml",
        "views/ai_menu.xml",
    ],
    "assets": {
        "web.assets_backend": ["mogen_sop_ai/static/src/**/*.js", "mogen_sop_ai/static/src/**/*.xml", "mogen_sop_ai/static/src/**/*.scss"],
        "web.qunit_suite_tests": ["mogen_sop_ai/static/tests/**/*.js"],
    },
    "application": False,
    "installable": True,
}
