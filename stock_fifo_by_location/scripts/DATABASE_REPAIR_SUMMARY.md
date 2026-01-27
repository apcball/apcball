# Stock FIFO by Warehouse - Database Repair Summary

## Problem Identified

After implementing the `_run_fifo()` and `_create_out_svl()` fixes, we discovered that:

1. **Existing negative layers** (created before the fix) had `remaining_value = NULL`
2. **Positive layers** were not consumed by negative layers (remaining_qty was incorrect)
3. **Products showed** `total_qty = 0` but `remaining_qty > 0`

This affected **OUTLET warehouse** and other warehouses significantly.

## Root Cause

- Negative layers created **before** the code fix did not trigger `_run_fifo()` properly
- The `_run_fifo()` override was added but existing data was not recalculated
- Database had inconsistent state from previous cross-warehouse FIFO consumption

## Solutions Implemented

### 1. Fix NULL remaining_value (3,927 layers)
```sql
UPDATE stock_valuation_layer
SET remaining_value = 0.0
WHERE quantity < 0 AND remaining_value IS NULL;
```

### 2. Fix value mismatch (129 products first round + 15 products second round)
- Script: `scripts/fix_value_mismatch.py`
- Adjusted negative layer values to balance with positive layers
- Distributed adjustments proportionally across negative layers

### 3. Recalculate remaining_qty per warehouse (20,488 layers)
- Script: `scripts/recalculate_remaining_by_warehouse.py`
- Simulated FIFO consumption for each product in each warehouse
- Updated all remaining_qty and remaining_value fields
- **3,329 products** across **24 warehouses**

## Results

### Before Fix
```
OUTLET (OT01) - RS00006110:
- total_qty: 0.0
- total_value: 142.42
- remaining_qty: 19.0  ❌ WRONG
- remaining_value: 2045.10
```

### After Fix
```
OUTLET (OT01) - RS00006110:
- total_qty: 0.0
- total_value: 0.0 ✅
- remaining_qty: 0.0 ✅
- remaining_value: 0.0 ✅
```

### Database-wide Verification
```
Total products checked: 2,543
- Value mismatch (qty=0 but value≠0): 0 ✅
- Remaining mismatch (moved qty ≠ remaining diff): 0 ✅
```

## Scripts Created

1. **fix_value_mismatch.py**
   - Purpose: Fix products where qty=0 but value≠0
   - Location: `scripts/fix_value_mismatch.py`
   - Usage: Auto-detects and fixes value discrepancies

2. **recalculate_remaining_by_warehouse.py**
   - Purpose: Recalculate remaining_qty per warehouse using FIFO
   - Location: `scripts/recalculate_remaining_by_warehouse.py`
   - Usage: Full database recalculation (safe to run multiple times)

3. **fix_valuation_by_warehouse.py** (existing)
   - Purpose: Initial remaining_qty fix (from earlier work)
   - Status: Superseded by recalculate_remaining_by_warehouse.py

## Module Version

**v17.0.1.1.4** - All fixes implemented and tested

### Key Changes:
- `_create_out_svl()` override to set warehouse_id before FIFO
- `_run_fifo()` override to respect warehouse boundaries
- `remaining_value: 0.0` instead of `0` to prevent NULL
- Database repair scripts for existing data

## Validation

Run these queries to verify:

```sql
-- Check for value mismatch
SELECT COUNT(*) FROM (
    SELECT pp.id
    FROM stock_valuation_layer svl
    JOIN product_product pp ON pp.id = svl.product_id
    GROUP BY pp.id
    HAVING ABS(SUM(svl.quantity)) < 0.01
       AND ABS(SUM(svl.value)) > 0.01
) sub;
-- Expected: 0

-- Check for remaining mismatch
SELECT COUNT(*) FROM (
    SELECT pp.id
    FROM stock_valuation_layer svl
    JOIN product_product pp ON pp.id = svl.product_id
    GROUP BY pp.id
    HAVING ABS(SUM(svl.quantity) - SUM(svl.remaining_qty)) > 0.01
) sub;
-- Expected: 0

-- Check for NULL remaining_value
SELECT COUNT(*)
FROM stock_valuation_layer
WHERE quantity < 0 AND remaining_value IS NULL;
-- Expected: 0
```

## Recommendation

For **new Odoo installations**, the module will work correctly from the start. For **existing databases** with historical data:

1. Install the module
2. Run `recalculate_remaining_by_warehouse.py` once
3. Run `fix_value_mismatch.py` to clean up any rounding issues
4. Verify using validation queries above

## Files Modified/Created

- `models/stock_move.py` - Added `_create_out_svl()` override
- `models/stock_valuation_layer.py` - Fixed `_run_fifo()` to use 0.0
- `scripts/fix_value_mismatch.py` - NEW
- `scripts/recalculate_remaining_by_warehouse.py` - NEW
- `__manifest__.py` - Updated version history

---
Date: 2025-11-28
Database: MOG_Test
Status: ✅ Complete
