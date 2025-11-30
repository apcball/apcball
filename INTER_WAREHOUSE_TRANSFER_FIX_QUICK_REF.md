# Inter-Warehouse Transfer Fix - Quick Reference

## Version: 17.0.1.1.5

## Problem
When transferring stock from WH-A → WH-B:
- ✅ Negative layer created at WH-A (outgoing)
- ❌ **Positive layer NOT created at WH-B** (incoming)
- Result: WH-B has stock quantity but `remaining_qty = 0`
- When selling from WH-B: Cannot find FIFO layer → Uses wrong cost

## Solution

### Correct Logic for Inter-Warehouse Transfer A → B:

**1. Source Warehouse (WH-A) - "Outgoing"**
```python
# Negative layer
{
    'warehouse_id': WH-A,
    'quantity': -qty,
    'value': -cost_from_fifo,
    'remaining_qty': 0,
}
# Run _run_fifo() to consume from WH-A's FIFO queue
```

**2. Destination Warehouse (WH-B) - "Incoming" ⚠️ CRITICAL**
```python
# Positive layer - MUST create this!
{
    'warehouse_id': WH-B,
    'quantity': +qty,
    'value': +cost_from_fifo,
    'remaining_qty': qty,  # ← FIFO source for future sales from WH-B
    'remaining_value': cost,
}
```

## Key Changes

### 1. Enhanced `_ensure_inter_warehouse_valuation_layers()`
```python
# Check existing layers
has_negative_source = any(l.quantity < 0 and l.warehouse_id == source_wh)
has_positive_dest = any(l.quantity > 0 and l.warehouse_id == dest_wh)

# Create negative layer if needed
if not has_negative_source:
    neg_layer = create_negative_layer()
    neg_layer._run_fifo(-qty, company)  # Consume from source FIFO queue

# 🔴 CRITICAL: Create positive layer if needed
if not has_positive_dest:
    pos_layer = create_positive_layer()  # Becomes FIFO source at destination
```

### 2. Enhanced Logging
```python
_logger.info(f"📦 Inter-warehouse: {source} → {dest}")
_logger.info(f"💰 FIFO cost: {unit_cost:.4f}")
_logger.info(f"✅ Created NEGATIVE layer at {source}")
_logger.info(f"✅ Created POSITIVE layer at {dest}")
```

### 3. Added Test Script
```bash
odoo-bin shell -d <db> -c <config>
>>> execfile('tests/test_inter_warehouse_transfer.py')
>>> test_inter_warehouse_transfer(env)
```

## Files Modified

1. `models/stock_move.py` - Fixed `_ensure_inter_warehouse_valuation_layers()`
2. `models/stock_valuation_layer.py` - Enhanced `_run_fifo()` logging
3. `tests/test_inter_warehouse_transfer.py` - New test script
4. `__manifest__.py` - Updated to v17.0.1.1.5

## Result

### Before ❌
```
Transfer WH-A → WH-B (5 units):
  WH-A: negative layer (qty=-5)
  WH-B: NO LAYER ← Problem!

Sale from WH-B (3 units):
  ❌ No layer found → Uses layer from WH-A → Wrong cost!
```

### After ✅
```
Transfer WH-A → WH-B (5 units):
  WH-A: negative layer (qty=-5, remaining=0)
  WH-B: positive layer (qty=+5, remaining=5) ← Created!

Sale from WH-B (3 units):
  ✅ Found layer at WH-B → Consume 3 → remaining=2
  ✅ Correct FIFO cost from WH-B's queue
```

## Installation

```bash
# 1. Upgrade module
odoo-bin -u stock_fifo_by_location -d <db> -c <config> --stop-after-init

# 2. Restart Odoo
sudo systemctl restart instance1

# 3. Test
odoo-bin shell -d <db> -c <config>
>>> execfile('tests/test_inter_warehouse_transfer.py')
>>> test_inter_warehouse_transfer(env)
```

## Benefits

1. ✅ Both layers always created (negative + positive)
2. ✅ Prevents duplicate layer creation
3. ✅ Correct FIFO cost at destination warehouse
4. ✅ Detailed logging for debugging
5. ✅ Comprehensive test coverage
6. ✅ No impact on standard Odoo behavior
