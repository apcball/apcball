# -*- coding: utf-8 -*-
{
    'name': 'Buz Unbuild State',
    'version': '17.0.1.0.0',
    'category': 'Manufacturing',
    'summary': 'Add picking state to unbuild orders',
    'description': """
        Extend the standard unbuild order flow with an optional picking step.

        Workflow:
        * draft
        * picking (optional stock picking creation)
        * done
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'license': 'LGPL-3',
    'depends': [
        'mrp',
        'stock',
    ],
    'data': [
        'security/security.xml',
        'views/mrp_unbuild_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
