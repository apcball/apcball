{
    'name': 'Buz Stock FIFO by Warehouse',
    'version': '17.0.1.1.0',
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
Stock FIFO by Warehouse with Landed Cost Support
================================================

This module extends Odoo 17's stock valuation system to support FIFO (First-In-First-Out)
cost accounting on a per-warehouse basis. Each stock valuation layer now includes a warehouse
reference, ensuring that COGS calculations and inventory valuations are correct when managing
inventory across multiple warehouses.

Core Features:
- Adds warehouse_id field to stock.valuation.layer for per-warehouse FIFO tracking
- Automatic population of warehouse_id when receiving/transferring/delivering inventory
- Independent FIFO queue for each warehouse - no mixing between warehouses
- Intra-warehouse moves properly tracked with warehouse_id (no skipping)
- Inter-warehouse transfers properly track cost flow between warehouses
- FIX v17.0.1.1.0: Enhanced validation and landed cost tracking
  * Added warehouse consistency constraint
  * Return moves now include landed costs
  * Improved landed cost transfer validation
- Shortage handling with configurable fallback policy
- Migration script for existing valuation layers
- Full integration with Odoo 17 stock and stock_account modules

NEW: Landed Cost Support by Warehouse
- Per-warehouse landed cost tracking with stock.valuation.layer.landed.cost model
- Automatic landed cost allocation during inter-warehouse transfers
- Proportional landed cost distribution based on quantity transferred
- Audit trail for all cost allocations via stock.landed.cost.allocation
- Service method: calculate_fifo_cost_with_landed_cost() for accurate COGS
- Full integration with stock_landed_costs module
- Enhanced validation to prevent negative values
- Comprehensive landed cost tests

Multi-Warehouse Scenarios:
- Inter-warehouse transfers automatically allocate landed costs
- Transit locations fully supported for multi-warehouse transfers
- Intra-warehouse moves properly tracked in warehouse FIFO queue
- Return moves preserve original cost including landed costs
- Shortage handling with optional fallback to other warehouses
- Cascading transfers maintain accurate landed cost tracking
- Comprehensive unit and integration tests

Key Benefits:
✓ True warehouse-level FIFO: Each warehouse maintains its own independent FIFO queue
✓ Cost propagation: Accurate cost transfer when moving between warehouses
✓ Landed cost accuracy: 100% accurate landed cost tracking per warehouse
✓ Data integrity: Validation ensures all layers have proper warehouse assignment
✓ Return accuracy: Returns use original cost including landed costs

Requirements:
- Odoo 17 with stock and stock_account modules installed
- stock_landed_costs module for landed cost functionality

Version History:
- 17.0.1.1.0: Fixed intra-warehouse logic, added validation, enhanced return move handling
- 17.0.1.0.9: Previous stable version
    ''',
}
