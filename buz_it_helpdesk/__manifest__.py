{
    'name': 'IT Helpdesk',
    'version': '17.0.1.3.5',
    'category': 'Services/Helpdesk',
    'summary': 'Standalone IT Helpdesk Phase 1',
    'description': """
Standalone IT Helpdesk Phase 1.

Provides the initial Helpdesk menu structure and basic ticket management
without dependencies on custom or business modules.
    """,
    'author': 'BUZ',
    'license': 'LGPL-3',
    'depends': ['base', 'hr', 'mail'],
    'data': [
        'data/sequence.xml',
        'data/stage_data.xml',
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/helpdesk_category_views.xml',
        'views/helpdesk_team_views.xml',
        'views/helpdesk_stage_views.xml',
        'views/helpdesk_ticket_views.xml',
        'views/helpdesk_line_settings_views.xml',
        'views/helpdesk_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'buz_it_helpdesk/static/src/js/helpdesk_attachment_preview.js',
            'buz_it_helpdesk/static/src/js/helpdesk_ticket_kanban_visibility.js',
            'buz_it_helpdesk/static/src/js/helpdesk_line_settings.js',
            'buz_it_helpdesk/static/src/xml/helpdesk_attachment_preview.xml',
            'buz_it_helpdesk/static/src/xml/helpdesk_line_settings.xml',
            'buz_it_helpdesk/static/src/scss/helpdesk_attachment_preview.scss',
            'buz_it_helpdesk/static/src/scss/helpdesk_ticket_kanban.scss',
            'buz_it_helpdesk/static/src/scss/helpdesk_line_settings.scss',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
