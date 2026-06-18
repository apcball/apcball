# -*- coding: utf-8 -*-
{
    'name': 'IT Request',
    'version': '17.0.1.0.0',
    'category': 'Helpdesk',
    'summary': 'IT Request Management (dev feature, error, equipment repair)',
    'description': """
IT Request Management
=====================

This module lets users open IT requests of three kinds:
- Dev / Feature requests (ask the dev team to develop/enhance a module)
- Error / Bug reports
- Equipment repair requests

Features:
* Unified it.request model with request_type discriminator
* Lightweight single-flow lifecycle (draft -> submitted -> in_progress -> waiting -> done / cancel)
* Assignment to IT/dev officers
* mail.thread chatter and mail.activity.mixin activities
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
    'demo': [],
    'installable': True,
    'auto_install': False,
    'application': True,
    'sequence': 100,
}