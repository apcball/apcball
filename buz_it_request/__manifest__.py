{
    'name': 'IT Request',
    'version': '17.0.4.0.0',
    'category': 'Helpdesk',
    'summary': 'IT Request Management (report problem, feature request)',
    'description': """
IT Request Management
=====================

For reporting system problems or requesting new features/enhancements.
Employees select category, enter subject, then describe request/problem.

Features:
* Employee-based requester (hr.employee) with auto-fill department, location, contact
* Category and sub-category classification
* IT Team assignment
* Impact / Urgency / Priority tracking
* SLA deadline with auto-compute (based on priority)
* SLA state tracking (On Track / At Risk / Breached)
* Resolution notes
* Request types: Report Problem / Feature Request / IT Equipment Purchase / IT Equipment Repair
* Simple lifecycle (draft → submitted → in_progress → waiting → done / cancel)
* Kanban with color-coded priorities
* mail.thread chatter
* Three-tier security groups (user / officer / manager)
    """,
    'author': 'BUZ',
    'website': 'https://www.buz.co.th',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'hr',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'views/it_request_views.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'buz_it_request/static/src/scss/it_request_kanban.scss',
            'buz_it_request/static/src/scss/it_request_form.scss',
        ],
    },
    'demo': [],
    'installable': True,
    'auto_install': False,
    'application': True,
    'sequence': 100,
}
