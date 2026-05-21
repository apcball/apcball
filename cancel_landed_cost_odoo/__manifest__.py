# -*- coding: utf-8 -*-
{
    'name': "Cancel Landed Cost",
    'version': "17.0.1.0.2",
    'category': 'Purchases,Accounting,Warehouse',
    'summary': 'Cancel landed costs with proper revert of journal entries and SVL',
    'description': """
        Cancel Landed Costs with three modes:
        - Cancel Only
        - Cancel and Reset to Draft
        - Cancel and Delete

        Properly reverts: vendor bill lines, journal entries,
        stock valuation layers, and product cost price.
    """,
    'author': 'Cybrosys Techno Solutions, Modified by Ball',
    'depends': ['account', 'purchase', 'stock_landed_costs'],
    'data': [
        'security/cancel_landed_cost_odoo_groups.xml',
        'data/stock_landed_cost_data.xml',
        'views/stock_landed_cost_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'license': 'AGPL-3',
    'installable': True,
    'auto_install': False,
    'application': False,
}
