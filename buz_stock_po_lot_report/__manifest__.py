{
    'name': 'Tax Stock Report with PO Lots',
    'version': '17.0.2.5.0',
    'summary': 'รายงานสินค้าและวัตถุดิบ: per-product ledger + ending lots',
    'category': 'Inventory/Reports',
    'depends': ['stock', 'stock_account', 'report_xlsx',
                'stock_fifo_by_location', 'stock_fifo_valuation_report'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/po_lot_views.xml',
        'report/po_lot_report.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
