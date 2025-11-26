# Fix for 0.00 Valuation in Inter-Warehouse Transfers

## Problem Report
**Database**: MOG_LIVE_15_08 (Production)  
**Symptom**: Inter-warehouse transfers showing 0.00 valuation  
**Example**: Transfer FG10/OB-DE/00267  
**User Report**: "ต่าง warehouse ตัด valuation ผิด เป็น 0"

## Root Cause Analysis

The module `stock_fifo_by_location` was attempting to create its own valuation layers during inter-warehouse transfers instead of using Odoo's standard valuation layer creation process.

### What Was Wrong

1. **Custom Layer Creation**: Method `_create_valuation_layers_for_inter_warehouse_transfer()` (~100 lines) was:
   - Manually calling `fifo_service.calculate_fifo_cost_with_landed_cost()`
   - Creating `outgoing_layer` (negative) and `incoming_layer` (positive) records
   - Setting `unit_cost` and `value` based on FIFO calculation

2. **Conflict with Odoo Standard**: 
   - Odoo's `stock_account` module already creates valuation layers in `_action_done()`
   - When our custom method also created layers, it caused conflicts
   - FIFO calculation sometimes returned 0.0 (no inventory at warehouse yet)
   - This resulted in layers with 0.00 values

3. **Wrong Architecture**:
   ```python
   # OLD (WRONG) - Creates duplicate layers
   def _action_done(self):
       result = super()._action_done()  # Odoo creates layers here
       self._create_valuation_layers_for_inter_warehouse_transfer()  # We create again!
       return result
   ```

## Solution Implemented

### Core Principle
**Don't create layers - just enhance them**

Let Odoo standard process create the valuation layers with correct values, then our module only adds the `warehouse_id` field to track which warehouse each layer belongs to.

### New Architecture

```python
# NEW (CORRECT) - Only enhances existing layers
def _action_done(self, cancel_backorder=False):
    # Call parent - Odoo creates layers with correct values
    result = super()._action_done(cancel_backorder=cancel_backorder)
    
    # Just add warehouse_id to already-created layers
    self._update_created_layers_warehouse()
    
    # Handle landed cost allocation separately
    self._allocate_landed_cost_for_inter_warehouse()
    
    return result
```

### Method Changes

1. **Removed**: `_create_valuation_layers_for_inter_warehouse_transfer()` (~100 lines)
   - This was creating layers manually
   - Caused 0.00 values when FIFO returned 0.0

2. **Simplified**: `_update_created_layers_warehouse()`
   - Finds layers created by Odoo standard: `search([('stock_move_id', '=', move.id)])`
   - Sets `warehouse_id` based on layer quantity:
     * Negative quantity → source warehouse
     * Positive quantity → destination warehouse

3. **Preserved**: `_allocate_landed_cost_for_inter_warehouse()`
   - Still handles landed cost allocation
   - But works with existing layers, doesn't create new ones

## Code Cleanup

### Files Modified
- `/opt/instance1/odoo17/custom-addons/stock_fifo_by_location/models/stock_move.py`

### Changes Made

1. **Line ~114-127**: Updated `_action_done()` method
   - Removed call to deleted method
   - Simplified to two calls: update warehouse, allocate landed cost

2. **Line ~129-162**: Simplified `_update_created_layers_warehouse()`
   - Now searches for existing layers instead of creating new ones
   - Only sets `warehouse_id` field

3. **Line ~164-183**: Updated `_allocate_landed_cost_for_inter_warehouse()`
   - Changed to search for existing layers
   - Removed variables: `current_cost`, `outgoing_layer`, `incoming_layer`

4. **Deleted**: ~100 lines of `_create_valuation_layers_for_inter_warehouse_transfer()`
   - Removed all manual layer creation logic
   - Removed FIFO cost calculation calls
   - Removed layer.create() calls

5. **Fixed**: Removed duplicate code fragments
   - Several orphaned code blocks from incomplete deletions
   - Duplicate method definitions

## Testing Required

### Before Upgrading Production

1. **Test Environment Setup**
   ```bash
   # Create test database copy
   sudo -u postgres pg_dump MOG_LIVE_15_08 | sudo -u postgres psql MOG_TEST
   
   # Restart Odoo pointing to test database
   sudo systemctl restart odoo17
   ```

2. **Module Upgrade**
   ```bash
   # In Odoo UI
   Apps → stock_fifo_by_location → Upgrade
   ```

3. **Test Cases**

   a. **Inter-Warehouse Transfer**
      - Create transfer from Warehouse A to Warehouse B
      - Product must have existing inventory in Warehouse A
      - Verify valuation layers:
        * Negative layer at Warehouse A with correct value
        * Positive layer at Warehouse B with same value
        * Both values should match product cost (not 0.00)

   b. **Intra-Warehouse Transfer**
      - Create transfer within same warehouse (Location A → Location B)
      - Verify layers have same warehouse_id
      - Verify no duplicate layers created

   c. **Existing Transfers**
      - Check historical transfers still show correct values
      - Query: `SELECT * FROM stock_valuation_layer WHERE stock_move_id = <move_id>`

4. **Validation Queries**

   ```sql
   -- Check for 0.00 valuation layers
   SELECT id, stock_move_id, product_id, warehouse_id, quantity, value
   FROM stock_valuation_layer
   WHERE value = 0.0 AND quantity != 0.0
   ORDER BY create_date DESC
   LIMIT 100;
   
   -- Check recent inter-warehouse transfers
   SELECT svl.id, sm.name, sm.product_id, svl.warehouse_id, svl.quantity, svl.value
   FROM stock_valuation_layer svl
   JOIN stock_move sm ON svl.stock_move_id = sm.id
   WHERE svl.create_date > NOW() - INTERVAL '1 day'
   ORDER BY svl.create_date DESC;
   ```

## Production Deployment

### Pre-Deployment Checklist
- [ ] Test environment validation passed
- [ ] All test cases executed successfully
- [ ] Backup created: `pg_dump MOG_LIVE_15_08`
- [ ] Maintenance window scheduled
- [ ] Rollback plan prepared

### Deployment Steps

1. **Backup Database**
   ```bash
   sudo -u postgres pg_dump MOG_LIVE_15_08 > /backup/MOG_LIVE_15_08_$(date +%Y%m%d_%H%M%S).sql
   ```

2. **Stop Odoo (if preferred)**
   ```bash
   sudo systemctl stop odoo17
   ```

3. **Upgrade Module**
   ```bash
   # Via command line
   /opt/odoo17/odoo-bin -c /etc/odoo17.conf -d MOG_LIVE_15_08 -u stock_fifo_by_location --stop-after-init
   
   # OR via UI (recommended)
   sudo systemctl start odoo17
   # Navigate to Apps → stock_fifo_by_location → Upgrade
   ```

4. **Verify Installation**
   - Check logs: `sudo tail -f /var/log/odoo17/odoo.log`
   - Test new inter-warehouse transfer
   - Check valuation layers have correct values

### Rollback Plan

If issues occur:
```bash
# Stop Odoo
sudo systemctl stop odoo17

# Restore database
sudo -u postgres psql <<EOF
DROP DATABASE MOG_LIVE_15_08;
CREATE DATABASE MOG_LIVE_15_08;
EOF
sudo -u postgres psql MOG_LIVE_15_08 < /backup/MOG_LIVE_15_08_YYYYMMDD_HHMMSS.sql

# Restart Odoo
sudo systemctl start odoo17
```

## Expected Results

### After Fix
- Inter-warehouse transfers will show **correct valuation** (not 0.00)
- Values will match product cost from source warehouse
- Landed costs will be properly allocated between warehouses
- Each warehouse maintains independent FIFO queue

### Example
Before Fix:
```
Transfer: WH1 → WH2, Product A, 10 units
Layer 1: WH1, -10 units, 0.00 value  ❌ WRONG
Layer 2: WH2, +10 units, 0.00 value  ❌ WRONG
```

After Fix:
```
Transfer: WH1 → WH2, Product A, 10 units @ $5/unit
Layer 1: WH1, -10 units, -$50.00 value  ✅ CORRECT
Layer 2: WH2, +10 units, +$50.00 value  ✅ CORRECT
```

## Technical Notes

### Why This Approach Works

1. **Odoo Standard Process**:
   - `stock_account` module already handles valuation correctly
   - Uses FIFO/AVCO based on product costing method
   - Creates layers with proper `value` calculation

2. **Our Enhancement**:
   - Only adds `warehouse_id` field for tracking
   - Doesn't interfere with value calculation
   - Maintains compatibility with Odoo standard

3. **Separation of Concerns**:
   - Odoo: Creates layers with values
   - Our module: Adds warehouse tracking
   - Clean, maintainable architecture

### Migration Impact

The migration scripts (`17.0.1.0.4/pre-migrate.py` and `post-migrate.py`) still work correctly:
- Add `warehouse_id` column to existing tables
- Migrate data from `location_id` to `warehouse_id`
- Don't affect value calculations

## Related Files

- `models/stock_move.py` - Main changes
- `models/stock_valuation_layer.py` - Warehouse field definition
- `models/fifo_service.py` - FIFO calculation service
- `models/landed_cost_location.py` - Landed cost tracking
- `migrations/17.0.1.0.4/` - Database migration scripts

## References

- Original Issue: "ต่าง warehouse ตัด valuation ผิด เป็น 0 database MOG_LIVE_15_08"
- Screenshot: FG10/OB-DE/00267 showing 0.00 values
- Module: stock_fifo_by_location v17.0.1.0.3 → 17.0.1.0.4

---
**Status**: Fixed and ready for testing  
**Date**: 2024  
**Version**: 17.0.1.0.4  
**Severity**: Critical - Production Bug  
**Priority**: High - Affects financial reporting
