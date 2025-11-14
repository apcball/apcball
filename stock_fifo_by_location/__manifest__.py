{
    'name': 'Buz Stock FIFO by Location',
    'version': '17.0.1.0.0',
    'category': 'Inventory/Stock',
    'author': 'APC Ball',
    'website': 'https://github.com/apcball/apcball',
    'license': 'LGPL-3',
    'depends': [
        'stock',
        'stock_account',
    ],
    'data': [
        'data/config_parameters.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
    'external_dependencies': {
        'python': [],
    },
    'description': '''
Stock FIFO by Location
======================

This module extends Odoo 17's stock valuation system to support FIFO (First-In-First-Out)
cost accounting on a per-location basis. Each stock valuation layer now includes a location
reference, ensuring that COGS calculations and inventory valuations are correct when managing
inventory across multiple storage locations.

Key Features:
- Adds location_id field to stock.valuation.layer for per-location FIFO tracking
- Automatic population of location_id when receiving/transferring/delivering inventory
- Shortage handling with configurable fallback policy
- Migration script for existing valuation layers
- Comprehensive unit and integration tests
- Full integration with Odoo 17 stock and stock_account modules

Requirements:
- Odoo 17 with stock and stock_account modules installed
    ''',
}
