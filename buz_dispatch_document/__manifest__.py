{
    'name': 'Buz Dispatch Document',
    'version': '17.0.1.0.0',
    'category': 'Inventory/Delivery',
    'summary': 'จัดการเอกสาร Dispatch สำหรับควบคุมเลขที่เอกสาร DO',
    'description': """
        โมดูลสำหรับสร้างเอกสาร Dispatch Document เพื่อควบคุมเลขที่เอกสาร Delivery Order
        - สร้าง Dispatch Document จาก stock picking
        - รันเลขที่เอกสารอัตโนมัติเมื่อกด Confirm
        - Validate เอกสารต้นทางจากหน้า Dispatch
        - Auto-validate ผ่าน Cron Job เวลา 05:00 น.
    """,
    'author': 'Ball',
    'website': '',
    'depends': [
        'stock',
        'sale_stock',
        'mail',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'data/cron.xml',
        'views/dispatch_document_views.xml',
        'views/stock_picking_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}