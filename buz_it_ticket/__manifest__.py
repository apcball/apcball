# -*- coding: utf-8 -*-
{
    'name': 'IT Ticket Management System',
    'version': '17.0.1.0.0',
    'category': 'Helpdesk/Support',
    'summary': 'Comprehensive IT ticketing system with Issue, Access, and Purchase workflows',
    'description': """
IT Ticket Management System
==========================

A comprehensive IT ticketing system that handles three main workflows:

1. Issue/Repair: Report problems → Work in progress → Request more info (if needed) → Resolved → Closed
2. Access: Requester → Manager approval → IT implementation → Closed
3. Purchase: Requester → Manager approval → IT verification → PO creation → Receive items → Closed

Features:
* Separate workflows for different ticket categories
* SLA tracking and breach notifications
* ISO-compliant reporting
* Dashboard with graphs and pivots
* Multi-company support
* Security groups with proper access rights
* Demo data for testing
    """,
    'author': 'Apcball',
    'website': 'https://www.buz.co.th',
    'license': 'LGPL-3',
    'depends': [
        'hr',
        'mail',
        'uom',
        'purchase',
        'web',
        # 'stock',  # Optional for equipment receiving
    ],
    'migration': {
        '17.0.1.0.0': [
            'migrations/17.0.1.0.0/pre-migrate_priority_to_sla.py',
            'migrations/17.0.1.0.0/pre-migrate_issue_fields.py',
        ],
    },
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'data/sla_data.xml',
        'data/access_templates.xml',
        'data/mail_templates.xml',
        'data/cron_data.xml',
        'views/it_ticket_views.xml',
        'views/it_ticket_separate_forms.xml',
        'views/it_ticket_kanban.xml',
        'views/it_ticket_actions.xml',
        'views/it_ticket_view_links.xml',
        'views/it_dashboard_views.xml',
        'views/it_config_views.xml',
        'views/it_ticket_menu.xml',
    ],
    'demo': [
        # 'data/demo_data.xml',  # Commented temporarily for debugging
    ],
    'installable': True,
    'auto_install': False,
    'application': True,
    'sequence': 100,
    'images': ['static/description/icon.png', 'static/description/banner.png'],
    'assets': {
        'web.assets_backend': [
            'buz_it_ticket/static/src/js/it_ticket.js',
            'buz_it_ticket/static/src/css/style.css',
        ],
    },
}