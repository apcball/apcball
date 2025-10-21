{
    'name': 'BUZ Accounting E-Tax Integration',
    'version': '17.0.1.0.0',
    'category': 'Accounting',
    'summary': 'การเชื่อมต่อระบบ E-Tax สำหรับส่งใบกำกับภาษี',
    'description': '''
        โมดูลสำหรับการเชื่อมต่อและส่งข้อมูลใบกำกับภาษีไปยังระบบ E-Tax
        - รองรับการส่งใบกำกับภาษี/ใบส่งของ
        - ตั้งค่าการเชื่อมต่อ API
        - ติดตามสถานะการส่ง
        - ดาวน์โหลด PDF และ XML
    ''',
    'author': 'BUZ Team',
    'website': 'https://www.buzteam.com',
    'depends': ['base', 'account', 'sale'],
    'data': [
        'security/ir.model.access.csv',
        'data/etax_data.xml',
        'views/etax_config_views.xml',
        'views/etax_transaction_views.xml',
    ],
    'demo': [],
    'installable': True,
    'auto_install': False,
    'application': True,
    'license': 'LGPL-3',
}