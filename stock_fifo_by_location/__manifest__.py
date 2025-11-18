{
    'name': 'Buz Stock FIFO by Location',
    'version': '17.0.1.0.3',
    'category': 'Inventory/Stock',
    'author': 'APC Ball',
    'website': 'https://github.com/apcball/apcball',
    'license': 'LGPL-3',
    'depends': [
        'stock',
        'stock_account',
        'stock_landed_costs',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/config_parameters.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
    'external_dependencies': {
        'python': [],
    },
    'description': '''
Stock FIFO by Location with Landed Cost Support
================================================

This module extends Odoo 17's stock valuation system to support FIFO (First-In-First-Out)
cost accounting on a per-location basis. Each stock valuation layer now includes a location
reference, ensuring that COGS calculations and inventory valuations are correct when managing
inventory across multiple storage locations.

Core Features:
- Adds location_id field to stock.valuation.layer for per-location FIFO tracking
- Automatic population of location_id when receiving/transferring/delivering inventory
- Shortage handling with configurable fallback policy
- Migration script for existing valuation layers
- Full integration with Odoo 17 stock and stock_account modules

NEW: Landed Cost Support
- Per-location landed cost tracking with stock.valuation.layer.landed.cost model
- Automatic landed cost allocation during internal transfers
- Proportional landed cost distribution based on quantity transferred
- Audit trail for all cost allocations via stock.landed.cost.allocation
- Service method: calculate_fifo_cost_with_landed_cost() for accurate COGS
- Full integration with stock_landed_costs module
- Comprehensive landed cost tests

Multi-Warehouse Scenarios:
- Internal transfers between locations automatically allocate landed costs
- Transit locations fully supported for inter-warehouse transfers
- Shortage handling with optional fallback to alternative locations
- Cascading transfers maintain accurate landed cost tracking
- Comprehensive unit and integration tests

Requirements:
- Odoo 17 with stock and stock_account modules installed
- stock_landed_costs module for landed cost functionality
    ''',
}
