{
    'name': 'Office Supply Requisition',
    'summary': 'ระบบเบิกจ่ายของในสำนักงาน ใช้งานได้ทั้งคอมและมือถือ',
    'version': '17.0.1.0.0',
    'category': 'Inventory',
    'author': 'Your Company',
    'license': 'LGPL-3',
    'depends': ['base', 'stock', 'hr', 'mail'],
    'data': [
        'security/groups.xml',
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'views/requisition_views.xml',
        'views/dashboard_views.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'office_supply_requisition/static/src/css/requisition.css',
            'office_supply_requisition/static/src/css/requisition_hybrid.css',
        ],
    },
    'installable': True,
    'application': True,
}
