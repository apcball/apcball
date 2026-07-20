# Copyright 2026 Mogen Co., Ltd.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

{
    "name": "MO Analytic Distribution Access",
    "summary": "Allow selected users to edit analytic distribution on manufacturing orders",
    "version": "17.0.1.0.0",
    "category": "Manufacturing",
    "license": "LGPL-3",
    "depends": ["mrp_account", "analytic"],
    "data": [
        "security/security.xml",
        "views/mrp_production_views.xml",
    ],
    "installable": True,
    "application": False,
}
