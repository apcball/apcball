{
    'name': 'Mogen Landed Cost MO Filter',
    'version': '17.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Filter manufacturing orders from landed costs by analytic account and date',
    'author': 'Mogen',
    'license': 'LGPL-3',
    'depends': ['mrp_landed_costs', 'analytic'],
    'data': [
        'views/stock_landed_cost_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
