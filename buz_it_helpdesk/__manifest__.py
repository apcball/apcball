{
    "name": "BUZ IT Helpdesk",
    "version": "17.0.1.0.0",
    "category": "Services/Helpdesk",
    "summary": "Standalone IT Helpdesk for BUZ IT Management Phase 1",
    "author": "Mogen Co.",
    "license": "LGPL-3",
    "depends": ["base", "mail"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/sequence.xml",
        "data/helpdesk_data.xml",
        "views/helpdesk_views.xml",
        "views/helpdesk_menus.xml",
    ],
    "application": True,
    "installable": True,
}
