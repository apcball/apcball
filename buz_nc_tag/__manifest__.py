{
    'name': 'NC Tag Print',
    'version': '17.0.1.0.0',
    'category': 'Inventory/Stock Management',
    'summary': 'Print NC TAG (FM-QAM-25) per unit from TAG internal transfers',
    'description': """
Adds a "Print NC Tag" button on transfers whose operation type is flagged
as NC Tag. One tag page is printed per unit (move line qty 10 -> 10 tags).
""",
    'author': 'Mogen Co., Ltd.',
    'license': 'LGPL-3',
    'depends': ['stock', 'buz_transfer_department'],
    'data': [
        'report/nc_tag_report.xml',
        'views/stock_picking_type_views.xml',
        'views/stock_picking_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
