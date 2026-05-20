# -*- coding: utf-8 -*-
{
    "name": "Buz Unbuild State Guard",
    "version": "17.0.1.0.0",
    "category": "Manufacturing",
    "summary": "Force unbuild orders through a picking step before completion",
    "description": """
        Enforce a safer unbuild workflow:
        draft -> picking -> done
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
