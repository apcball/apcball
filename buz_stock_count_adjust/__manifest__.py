{
    'name': 'Stock Count Adjustment (FIFO void-reseed)',
    'version': '17.0.1.1.0',
    'category': 'Inventory/Inventory',
    'author': 'APC Ball',
    'license': 'LGPL-3',
    'depends': [
        'stock', 'stock_account',
        'stock_fifo_by_location',
        'stock_fifo_valuation_report',
        'stock_fifo_by_warehouse_recal',
    ],
    'data': [
        'security/count_adjust_security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'views/stock_count_adjustment_views.xml',
        'views/stock_count_adjustment_backup_views.xml',
        'views/stock_count_adjustment_import_views.xml',
    ],
    'installable': True,
    'application': False,
}
