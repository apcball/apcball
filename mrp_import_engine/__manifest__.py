# -*- coding: utf-8 -*-
{
    'name': "MRP Import Engine",
    'summary': "Import BOM and Manufacturing Order (MO) via Excel/JSON",
    'description': """
MRP Import Engine
=================
- Import BOM and MO through external APIs or file uploads
- Built-in validation layers and staging tables
- Queue Job integration for async processing
- Replay engine support for MOs
    """,
    'author': "Developer",
    'website': "",
    'category': 'Manufacturing/Manufacturing',
    'version': '17.0.1.0.0',
    'depends': ['mrp'],
    'data': [
        'security/mrp_import_security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'views/mrp_import_views.xml',
    ],
    'application': False,
    'installable': True,
}
