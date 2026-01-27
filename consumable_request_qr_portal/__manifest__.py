# -*- coding: utf-8 -*-
{
    'name': 'Consumable Request QR Portal',
    'version': '17.0.1.0.0',
    'category': 'Inventory',
    'summary': 'QR Code Portal for Consumable Request Receive',
    'description': """
        Extension for Internal Consumable Request System
        ================================================
        * QR Code generation after approval
        * Mobile-first Portal page (no login required)
        * Digital signature on receive
        * Automatic Internal Stock Transfer
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'license': 'LGPL-3',
    'depends': [
        'internal_consume_request',
        'stock',
        'portal',
        'website',
        'mail',
        'web',
    ],
    'data': [
        'views/consumable_request_view.xml',
        'views/portal_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'consumable_request_qr_portal/static/src/css/portal.css',
            'consumable_request_qr_portal/static/src/js/signature_pad.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
