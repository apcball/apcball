{
    "name": "IT Helpdesk",
    "version": "17.0.1.0.0",
    "category": "Helpdesk",
    "summary": "Standalone IT helpdesk ticket management",
    "description": """
Standalone IT Helpdesk
======================

A lightweight, self-contained helpdesk module for managing internal IT tickets.

Features:
* Standalone ticket model
* My Tickets, Dashboard, and All Tickets menus
* Simple stage and priority tracking
* No dependency on other custom modules
    """,
    "author": "BUZ",
    "website": "https://www.buz.co.th",
    "license": "LGPL-3",
    "depends": [
        "base",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/sequence.xml",
        "views/buz_it_ticket_views.xml",
        "views/menu.xml",
    ],
    "demo": [],
    "installable": True,
    "auto_install": False,
    "application": True,
    "sequence": 100,
}
