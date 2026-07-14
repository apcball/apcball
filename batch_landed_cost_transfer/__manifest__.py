{
    'name': 'BUZ Batch Transfer Landed Cost Helper',
    'version': '17.0.1.1.0',
    'summary': 'Auto-populate Landed Cost Transfers from Batch Transfer(s)',
    'description': """
        Updates Landed Cost UX to allow selecting one or more Batch Transfers.
        Automatically pulls all valid incoming transfers from the selected batches into the Landed Cost.
    """,
    'category': 'Inventory/Inventory',
    'author': 'Your Company',
    'depends': ['stock_landed_costs', 'stock_picking_batch'],
    'data': [
        'security/ir.model.access.csv',
        'views/stock_landed_cost_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
