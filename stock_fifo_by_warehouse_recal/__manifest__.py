# -*- coding: utf-8 -*-
{
    'name': 'FIFO Recalculation by Warehouse',
    'version': '17.0.3.1.0',
    'category': 'Inventory/Stock',
    'author': 'APC Ball',
    'website': 'https://github.com/apcball/apcball',
    'license': 'LGPL-3',
    'depends': [
        'stock',
        'stock_account',
        'stock_fifo_by_location',
        'stock_valuation_layer_usage',
    ],
    'data': [
        'security/fifo_recal_security.xml',
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'views/fifo_recalculation_wizard_views.xml',
        'views/fifo_recalculation_backup_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
    'description': '''
FIFO Recalculation by Warehouse - IMPROVED
===========================================

This module provides a wizard for recalculating FIFO valuation layers on a per-warehouse basis.

✅ NEW IMPROVEMENTS:
- Uses proper warehouse assignment logic from stock_fifo_by_location
- Correctly handles inter-warehouse transfers (both shipment and receipt)
- Supports cross-warehouse return moves
- Creates proper stock.valuation.layer.usage records for audit trail
- Handles transit locations properly
- Comprehensive backup of ALL product layers (including products without moves in date range)

Features:
- Select date range for recalculation
- Filter by warehouses, products, or product categories
- Preview impact before applying changes (Before/After comparison)
- Delete and rebuild valuation layers based on FIFO logic
- Lock recalculated layers to prevent duplicate recalculation
- Complete backup and rollback functionality for all affected products
- Multi-company support
- Dry run mode for testing
- Detailed logging of all operations

Backup Functionality:
- Backs up ALL layers for selected products/warehouses
- Includes products even if they have no moves in the selected date range
- Ensures complete rollback capability
- Tracks backup state and restore history

Use Cases:
- Period-end closing adjustments
- Fixing corrupted valuation layers from inter-warehouse transfers
- Data cleanup and reconciliation after warehouse migrations
- FIFO queue verification and correction
- Audit trail reconstruction

Requirements:
- stock_fifo_by_location module must be installed
- User must have Stock Manager rights or System Admin
    ''',
}
