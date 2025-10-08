{
    "name": "Internal Consumption Request",
    "version": "17.0.1.0.0",
    "summary": "Internal consumption with approval, stock moves, and accounting",
    "author": "Ball/MOGEN + Buz",
    "depends": ["base", "stock", "account", "mail", "analytic", "hr"],
    "data": [
        "security/ir.model.access.csv",
        "security/security.xml",
        "data/sequence.xml",
        "views/ic_settings_views.xml",
        "views/ic_request_views.xml",
        "views/menu.xml",
        "report/ic_request_report.xml",
    ],
    "demo": [
        "demo/ic_demo_data.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
}