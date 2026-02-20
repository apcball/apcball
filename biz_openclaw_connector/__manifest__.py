# -*- coding: utf-8 -*-
{
    "name": "Biz OpenClaw Connector",
    "version": "1.0.0",
    "category": "Accounting",
    "summary": "Connect Odoo to OpenClaw AI Audit Service",
    "description": """
OpenClaw AI Audit Connector
============================
This module integrates Odoo with the OpenClaw AI audit service.

Features:
- Configure OpenClaw API connection
- Queue jobs for AI processing
- Receive and manage AI suggestions
- Invoice AI audit integration
- Automated job processing via cron
    """,
    "author": "Business Solutions",
    "depends": ["base", "account"],
    "data": [
        "security/ir.model.access.csv",
        "security/security.xml",
        "views/openclaw_config_views.xml",
        "views/openclaw_job_views.xml",
        "views/openclaw_suggestion_views.xml",
        "views/account_move_views.xml",
        "data/openclaw_cron.xml",
    ],
    "assets": {},
    "installable": True,
    "application": True,
    "license": "LGPL-3",
}
