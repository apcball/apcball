{
    'name': 'Buz Dispatch Document',
    'version': '17.0.1.0.2',
    'category': 'Inventory/Delivery',
    'summary': 'จัดการเอกสาร Dispatch สำหรับควบคุมเลขที่เอกสาร DO',
    'description': """
        โมดูลสำหรับสร้างเอกสาร Dispatch Document เพื่อควบคุมเลขที่เอกสาร Delivery Order
        - สร้าง Dispatch Document จาก stock picking
        - รันเลขที่เอกสารอัตโนมัติเมื่อกด Confirm
        - Backdate เอกสาร Delivery ตามวันที่เอกสาร Dispatch
    """,
    'author': 'Ball',
    'website': '',
    'depends': [
        'stock',
        'sale_stock',
        'mail',
        'buz_inventory_delivery_report',
        'buz_delivery_report',
        'stock_picking_backdate_all',
    ],
    'assets': {
        'web.assets_backend': [
            'buz_dispatch_document/static/src/css/dispatch_document.css',
        ],
    },
    'data': [
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'views/dispatch_document_views.xml',
        'views/stock_picking_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}