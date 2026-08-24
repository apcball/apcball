{
    'name': 'Tag Inventory',
    'version': '17.0.1.0.0',
    'category': 'Inventory/Stock Management',
    'summary': 'Add colored Tags to stock pickings (Receipts, Deliveries, Internal Transfers)',
    'description': """
Tag Inventory
=============
Adds a many2many Tags field to stock.picking so pickings can be freely
classified/labeled.

- Form view: Tags field shown near Source Document.
- Tree view: Tags shown as an optional column.
- Configuration > Tags: manage tag names and colors.
""",
    'author': 'BUZ',
    'website': 'https://www.buz.co.th',
    'license': 'LGPL-3',
    'depends': ['stock'],
    'data': [
        'security/ir.model.access.csv',
        'views/picking_tag_views.xml',
        'views/stock_picking_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
