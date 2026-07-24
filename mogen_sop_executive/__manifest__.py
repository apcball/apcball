{
    "name": "Mogen Smart S&OP Executive",
    "summary": "Executive decision support foundation for Smart S&OP",
    "version": "17.0.1.0.0",
    "category": "Operations/Planning",
    "author": "Mogen Co., Ltd.",
    "license": "LGPL-3",
    "depends": ["mogen_sop_dashboard", "mogen_sop_scenario", "mogen_sop_risk", "mogen_sop_ai", "web"],
    "data": ["security/executive_security.xml", "security/ir.model.access.csv", "data/executive_data.xml", "views/executive_views.xml", "views/executive_menu.xml"],
    "assets": {
        "web.assets_backend": ["mogen_sop_executive/static/src/**/*.js", "mogen_sop_executive/static/src/**/*.xml", "mogen_sop_executive/static/src/**/*.scss"],
        "web.qunit_suite_tests": ["mogen_sop_executive/static/tests/**/*.js"],
    },
    "application": False,
    "installable": True,
}
