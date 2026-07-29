{
    'name': 'IT Helpdesk',
    'version': '17.0.1.0.0',
    'category': 'Services/Helpdesk',
    'summary': 'Standalone IT Helpdesk Phase 1',
    'description': """
Standalone IT Helpdesk Phase 1.

Provides the initial Helpdesk menu structure and basic ticket management
without dependencies on custom or business modules.
    """,
    'author': 'BUZ',
    'license': 'LGPL-3',
    'depends': ['base', 'hr'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'data/stage_data.xml',
        'views/helpdesk_category_views.xml',
        'views/helpdesk_team_views.xml',
        'views/helpdesk_stage_views.xml',
        'views/helpdesk_ticket_views.xml',
        'views/helpdesk_menus.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
