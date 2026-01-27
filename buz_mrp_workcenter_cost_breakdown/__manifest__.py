# -*- coding: utf-8 -*-
{
    'name': 'Work Center Cost Breakdown (DL / IDL / OH)',
    'version': '17.0.1.0.0',
    'category': 'Manufacturing',
    'summary': 'Add cost breakdown fields to Work Centers with DL, IDL, and OH per hour calculations',
    'description': """
        Work Center Cost Breakdown Module
        ==================================
        
        This module extends the MRP Work Center model to include detailed cost breakdown fields:
        
        Features:
        ---------
        * DL per Hour (Direct Labor cost per hour)
        * IDL per Hour (Indirect Labor cost per hour)
        * OH per Hour (Overhead cost per hour)
        * Automatic calculation of total Cost per Hour
        * Validation to prevent negative values
        * Clean UI with tooltips for better understanding
        
        Technical Details:
        ------------------
        * Extends mrp.workcenter model
        * Uses compute fields for automatic calculations
        * Includes validation constraints
        * Multi-company compatible
        * Ready for Odoo 17 Community/Enterprise
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'license': 'LGPL-3',
    'depends': [
        'mrp',
    ],
    'data': [
        'views/mrp_workcenter_view.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
    'sequence': 100,
    'images': [],
    'demo': [],
    'qweb': [],
    'post_init_hook': None,
    'pre_init_hook': None,
    'uninstall_hook': None,
    'external_dependencies': {},
}