{
    'name': 'BUZ Batch Transfer Landed Cost Helper',
    'version': '17.0.1.0.0',
    'summary': 'Auto-populate Landed Cost Transfers from Batch Transfer',
    'description': """
        Updates Landed Cost UX to allow selecting a Batch Transfer.
        Automatically pulls all valid incoming transfers from the batch into the Landed Cost.
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
