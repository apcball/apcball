# -*- coding: utf-8 -*-
{
    "name": "Buz Unbuild State Guard",
    "version": "17.0.2.0.0",
    "category": "Manufacturing",
    "summary": "Optional picking step for unbuild orders, with BOM component cost guard",
    "description": """
        Safer unbuild workflow:
        - draft -> picking -> confirm -> done (formal stock issuance)
        - draft -> done directly, when stock is already available ("Unbuild Directly")
        - blocks unbuild (either route) if any BOM component has zero cost
    """,
    "author": "Your Company",
    "website": "https://www.yourcompany.com",
    "license": "LGPL-3",
    "depends": [
        "mrp",
        "stock",
    ],
    "data": [
        "reports/unbuild_job_report.xml",
        "views/mrp_unbuild_views.xml",
    ],
    "assets": {
        "web.report_assets_common": [
            "/buz_unbuild_state_guard/static/fonts/Sarabun-Bold.ttf",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
