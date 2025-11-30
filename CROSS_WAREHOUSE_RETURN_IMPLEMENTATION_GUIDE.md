# Cross-Warehouse Return Implementation Guide
## Version 17.0.1.1.6

## Overview

Module `stock_fifo_by_location` now supports **cross-warehouse returns** - allowing customers to return products to a different warehouse than where they were originally sold.

## Use Case (ใช้งานจริง)

**เคส**: ขายสินค้าจาก WH-A แต่ลูกค้าคืนของเข้าคลัง WH-B

**ตัวอย่าง**:
- ขายจากคลังกรุงเทพ (Bangkok WH)
- ลูกค้าคืนของที่คลังเชียงใหม่ (Chiang Mai WH)
- ระบบจัดการต้นทุนและสต็อกอย่างถูกต้อง

## Technical Implementation

### 1. Cost Flow (การไหลของต้นทุน)

```
Original Sale (WH-A):
├─ Receive: 10 units @ 100 THB/unit → Layer at WH-A
├─ Deliver: 10 units (consumes FIFO from WH-A @ 100 THB/unit)
│
└─ Return to Different Warehouse (WH-B):
   ├─ Cost Source: Original FIFO cost from WH-A (100 THB/unit)
   ├─ Layer Location: Created at WH-B (where stock physically returns)
   └─ Result: WH-B has 10 units @ 100 THB/unit for future sales
```

### 2. Key Principles

1. **Cost Determinism**: Return uses the EXACT cost from original sale
   - Includes base cost + landed costs
   - No recalculation, no averaging
   - Same cost that was used when delivering to customer

2. **Layer Placement**: Layer created at DESTINATION warehouse
   - Stock physically returns to WH-B
   - WH-B can sell this stock using FIFO @ 100 THB/unit
   - No confusion about which warehouse owns the stock

3. **FIFO Scope**: Each warehouse maintains independent FIFO queue
   - WH-A: May have other stock at different costs
   - WH-B: Returned stock becomes part of its FIFO queue
   - No cross-warehouse mixing

### 3. Code Changes

#### Modified Methods

**`_get_fifo_valuation_layer_warehouse()`**
```python
# OLD: Return moves MUST use original warehouse
if self.origin_returned_move_id:
    return original_warehouse  # ❌ Forced to original

# NEW: Return moves use DESTINATION warehouse
if self.origin_returned_move_id:
    return self.location_dest_id.warehouse_id  # ✅ Flexible
```

**`_action_done()`**
```python
# OLD: Validation blocks cross-warehouse returns
if original_wh != return_wh:
    raise ValidationError("Cannot return to different warehouse")  # ❌

# NEW: Validation removed
# ✅ Cross-warehouse returns now allowed
```

**`_update_created_layers_warehouse()`**
```python
# Enhanced to handle cross-warehouse returns:
# 1. Get original_wh from original move (for cost calculation)
# 2. Get dest_wh from current move (for layer placement)
# 3. Use original_wh's FIFO cost
# 4. Create layer at dest_wh
```

### 4. Example Scenario

```python
# Step 1: Receive to WH-A
Receipt (WH-A): +10 units @ 100 THB
  → Layer: warehouse_id = WH-A, quantity = 10, unit_cost = 100

# Step 2: Deliver from WH-A
Delivery (WH-A): -10 units @ 100 THB (FIFO consumption)
  → Layer: warehouse_id = WH-A, quantity = -10, unit_cost = 100

# Step 3: Return to WH-B (CROSS-WAREHOUSE!)
Return (WH-B): +10 units @ 100 THB (cost from WH-A)
  → Negative Layer: warehouse_id = WH-B, quantity = -10, unit_cost = 100
  → Positive Layer: warehouse_id = WH-B, quantity = +10, unit_cost = 100

# Step 4: Sell from WH-B (using returned stock)
Delivery (WH-B): -5 units @ 100 THB (FIFO from returned stock)
  → Layer: warehouse_id = WH-B, quantity = -5, unit_cost = 100

# Final State:
# WH-A: 0 units
# WH-B: 5 units @ 100 THB
```

### 5. Valuation Layer Structure

For cross-warehouse return move:

```python
# Negative Layer (consumption at destination for FIFO accounting)
{
    'stock_move_id': return_move.id,
    'warehouse_id': warehouse_b.id,  # ✅ Destination warehouse
    'quantity': -10,
    'unit_cost': 100,  # ✅ From original WH-A FIFO
    'value': -1000,
}

# Positive Layer (new stock at destination)
{
    'stock_move_id': return_move.id,
    'warehouse_id': warehouse_b.id,  # ✅ Destination warehouse
    'quantity': 10,
    'unit_cost': 100,  # ✅ From original WH-A FIFO
    'value': 1000,
    'remaining_qty': 10,  # Available for future FIFO consumption
}
```

## Benefits

### 1. Business Flexibility
- Customers can return to nearest warehouse
- Reduces logistics costs
- Improves customer service

### 2. Cost Accuracy
- No guesswork on cost
- Uses original transaction cost
- Maintains audit trail

### 3. FIFO Integrity
- Each warehouse maintains independent queue
- No cross-warehouse contamination
- Predictable cost flow

### 4. Inventory Accuracy
- Stock shows in correct warehouse
- No phantom stock
- No negative balances

## Testing

### Test Cases Included

1. **`test_cross_warehouse_return_basic`**
   - Basic cross-warehouse return
   - Verifies cost and warehouse assignment

2. **`test_cross_warehouse_return_then_sell_from_new_warehouse`**
   - Return to WH-B, then sell from WH-B
   - Verifies FIFO queue works at new warehouse

3. **`test_cross_warehouse_return_preserves_cost_determinism`**
   - Multiple receipts at different costs
   - Verifies return uses original FIFO cost, not average

4. **`test_cross_warehouse_return_no_negative_balance`**
   - Verifies no negative remaining_qty
   - Boundary testing

### Run Tests

```bash
# Run all FIFO tests
odoo-bin -c /etc/odoo.conf -d database_name -i stock_fifo_by_location --test-enable --log-level=test

# Run only cross-warehouse return tests
odoo-bin -c /etc/odoo.conf -d database_name --test-tags=stock_fifo_by_location.test_cross_warehouse_return
```

## Migration from Previous Version

### If Upgrading from 17.0.1.1.5 or Earlier

**No migration needed!**

The change is purely behavioral - previously blocked returns are now allowed.

### For Existing Cross-Warehouse Return Attempts

If you have failed return attempts due to validation error:
1. Simply recreate the return picking
2. System will now process it correctly
3. Cost will be calculated from original sale
4. Layer will be created at destination warehouse

## Configuration

No configuration needed. Feature works automatically.

## Troubleshooting

### Issue: Return cost is wrong

**Check**:
1. Verify `origin_returned_move_id` is set correctly
2. Check original move has valuation layers
3. Verify original warehouse has FIFO data

**Fix**: Ensure return is linked to original move:
```python
return_move.origin_returned_move_id = original_delivery_move.id
```

### Issue: Layer created at wrong warehouse

**Check**:
1. Verify `location_dest_id` is correct
2. Check warehouse assignment of destination location

**Fix**: Ensure destination location belongs to correct warehouse

### Issue: Cannot find FIFO cost from original warehouse

**Check**:
1. Original move has negative layer (consumption)
2. Original layer has `unit_cost` set
3. Original warehouse FIFO data exists

**Fix**: May need to recalculate valuation layers for original move

## API Reference

### Method: `_get_fifo_valuation_layer_warehouse()`

**Purpose**: Determine which warehouse a valuation layer should belong to

**For Return Moves**:
- Returns destination warehouse (where stock returns)
- Cost calculation happens separately using original warehouse

**Returns**: `stock.warehouse` record or None

### Method: `_update_created_layers_warehouse()`

**Purpose**: Update warehouse_id and unit_cost on valuation layers after creation

**For Return Moves**:
1. Finds original warehouse from `origin_returned_move_id`
2. Gets FIFO cost from original warehouse's layers
3. Sets `warehouse_id` to destination warehouse
4. Sets `unit_cost` to original FIFO cost

## Best Practices

### 1. Always Link Return to Original Move

```python
# ✅ Good
return_move.origin_returned_move_id = original_move.id

# ❌ Bad - unlinked return
return_move.origin_returned_move_id = False
```

### 2. Use Proper Return Wizard

Let Odoo's return wizard create the return:
- Automatically links to original move
- Sets correct quantities
- Maintains data integrity

### 3. Monitor Cross-Warehouse Returns

Create report to track:
- Returns to different warehouse
- Cost differences (if any)
- Frequency by customer/product

## Summary

**วิธีที่ปลอดภัยสุด (Safest Approach)**:

1. ✅ ตอน return ให้อิงจาก original out move ที่ SO/Invoice เดิม
2. ✅ เอา layer ที่เคยถูกใช้ตอนขาย (ใน WH-A) มาเป็น base cost
3. ✅ ตอนสร้าง SVL ฝั่ง return:
   - warehouse เป็นคลังที่ของเข้าจริง (WH-B)
   - แต่ใช้ cost = cost ที่ขายออกจาก WH-A

**ผลลัพธ์**:
- Cost กลับเข้ามาเก็บใน WH-B ตามเดิม
- FIFO scope: จากนี้ไป WH-B มี layer ใหม่ที่ cost ตาม original sale
- Cost flow จะยัง deterministic
- ไม่พัง FIFO
- ไม่งงว่าต้องย้อน layer กลับไป WH-A หรือไม่

## Version

- Module: `stock_fifo_by_location`
- Version: `17.0.1.1.6`
- Date: 30 พฤศจิกายน 2568
- Author: APC Ball
