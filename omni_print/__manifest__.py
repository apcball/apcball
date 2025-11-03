# -*- coding: utf-8 -*-
{
    'name': "Omni Print: Direct Print from Desktop",
    'summary': """Omni Print can simplify your print workflow with one single click, no more downloads required.""",
    'version': '1.1.0',
    'author': "Omni Byte",
    'website': "https://omni-byte.com/",
    'images': ['static/description/main_screenshot.png'],
    'support': "support@omni-byte.com",
    'live_test_url': 'https://demo.omni-byte.com/',
    'license': "OPL-1",
    'category': 'Printer',
    'price': 0,
    'currency': 'EUR',
    'depends': ['base', 'web'],
    'data': [
        'views/views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'omni_print/static/src/service/*',
            'omni_print/static/src/components/*',
            'omni_print/static/src/network/*',
        ],
    },
    'application': True,
}
