{
    'name': 'Buz Stock FIFO by Warehouse',
    'version': '17.0.1.1.5',
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
        'wizard/stock_valuation_recalculate_wizard_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
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
✓ Full Balance Zero: Return full quantity results in balance = 0

Requirements:
- Odoo 17 with stock and stock_account modules installed
- stock_landed_costs module for landed cost functionality

Version History:
- 17.0.1.1.5: CRITICAL FIX - Enhanced inter-warehouse transfer to ALWAYS create both layers
  * Fixed _ensure_inter_warehouse_valuation_layers() to create BOTH negative AND positive layers
  * Negative layer at source warehouse (consumes from FIFO queue)
  * Positive layer at destination warehouse (becomes new FIFO source)
  * Prevents issue where destination warehouse has stock quantity but no valuation layer
  * Without positive layer: remaining_qty = 0, sales fail to find FIFO layers
  * Enhanced logging in _run_fifo() and _ensure_inter_warehouse_valuation_layers()
  * Added comprehensive test script: test_inter_warehouse_transfer.py
  * Solves: ที่คลังปลายทางมี stock แต่ไม่มี layer → ขายไม่ได้หรือคำนวณผิด
- 17.0.1.1.4: CRITICAL FIX - Override _run_fifo() AND _create_out_svl() to respect warehouse boundaries
  * Added _run_fifo() override in stock.valuation.layer
  * Added _create_out_svl() override in stock.move to set warehouse_id BEFORE _run_fifo()
  * FIFO consumption now only from SAME warehouse (no cross-warehouse)
  * remaining_qty and remaining_value now calculated PER WAREHOUSE
  * Negative layers now have warehouse_id set during creation (not after)
  * Fixes issue where Remaining Qty != Moved Qty in valuation reports
  * Each warehouse maintains truly independent FIFO queue
  * Solves: ตัด stock ผิดคลัง causing incorrect valuation
- 17.0.1.1.3: CRITICAL FIX - Return moves now correctly identify original warehouse
  * Fixed _get_fifo_valuation_layer_warehouse() to get warehouse from location (not move.warehouse_id)
  * Fixed validation in _action_done() to properly detect original warehouse
  * Fixed _update_created_layers_warehouse() to correctly find original warehouse
  * Return moves now ALWAYS use warehouse from original move's INTERNAL location
  * Prevents cross-warehouse return issues causing negative balance
- 17.0.1.1.2: CRITICAL FIX - Return moves use FIFO cost WITH landed costs
  * Fixed unit_cost calculation for return layers
  * Return moves now consume from FIFO queue including landed costs
  * Added _copy_landed_cost_to_return() for proper landed cost allocation
  * Return full quantity now results in balance = 0 ✅
  * Test case: test_return_full_quantity_balance_equals_zero()
- 17.0.1.1.1: CRITICAL FIX - Prevent negative warehouse balance on returns
  * Return moves now FORCED to use original warehouse
  * Added validation in _action_done() to block cross-warehouse returns
  * Enhanced _check_warehouse_consistency() to detect negative balance
  * Thai error messages for better user understanding
- 17.0.1.1.0: Fixed intra-warehouse logic, added validation, enhanced return move handling
- 17.0.1.0.9: Previous stable version
    ''',
}
