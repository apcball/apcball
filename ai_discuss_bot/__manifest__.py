# -*- coding: utf-8 -*-
{
    'name': 'AI Discuss Bot',
    'version': '17.0.1.0.0',
    'category': 'Discuss',
    'summary': 'AI-powered Discuss bot for stock and document search',
    'description': """
AI Discuss Bot
==============
* Intercepts messages in a dedicated Discuss channel
* Answers stock quantity questions across warehouses
* Searches document numbers across sales, purchase, invoices, and pickings
* AI-powered responses with configurable API integration
* Keyword matching fallback when AI is unavailable
    """,
    'author': 'AI-DEV-Module-Odoo17',
    'website': 'https://github.com/apcball/AI-DEV-Module-Odoo17',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'stock',
        'sale_management',
        'purchase',
        'account',
    ],
    'data': [
        'security/res_groups.xml',
        'security/ir.model.access.csv',
        'views/mail_channel_views.xml',
        'views/ai_discuss_config_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'application': False,
    'installable': True,
}
