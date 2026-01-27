# -*- coding: utf-8 -*-
{
    'name': 'Consumable Request',
    'version': '17.0.1.0.0',
    'category': 'Inventory',
    'summary': 'ขอเบิกอุปกรณ์สิ้นเปลืองภายในบริษัท',
    'description': """
        Internal Consumable Request System
        ===================================
        * พนักงานสร้างเอกสารขอเบิก
        * ส่งอนุมัติไปยังหัวหน้า
        * สร้าง Delivery / Internal Transfer
        * ติดตาม Stock Level
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'hr',
        'stock',
        'mail',
        'account',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'wizard/wizard_reject_request_view.xml',
        'views/internal_consume_request_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
