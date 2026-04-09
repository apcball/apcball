# -*- coding: utf-8 -*-
{
    'name': "MRP Import Engine UI",
    'summary': "OWL UI for MRP Import Engine",
    'description': """
Provides Drag & Drop upload and Dashboard for MRP Import Engine using OWL.
    """,
    'author': "Developer",
    'category': 'Manufacturing/Manufacturing',
    'version': '17.0.1.0.0',
    'depends': ['mrp_import_engine', 'web'],
    'data': [
        'views/mrp_import_ui_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'mrp_import_engine_ui/static/src/services/*.js',
            'mrp_import_engine_ui/static/src/components/*.js',
            'mrp_import_engine_ui/static/src/xml/*.xml',
        ],
    },
    'application': False,
    'installable': True,
}
