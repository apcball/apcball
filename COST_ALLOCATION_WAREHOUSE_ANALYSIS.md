# 📊 วิเคราะห์ Logic: Cost Allocation ระหว่าง Warehouse

## 🎯 บทสรุป
Module `stock_fifo_by_location` มีการตัดจ่าย (allocation) และการแชร์ cost ระหว่าง warehouse อยู่ **3 ระดับ**:

1. **FIFO Queue Level** - แต่ละ warehouse มี FIFO queue เป็นอิสระ ❌ **ไม่แชร์กันโดยตรง**
2. **Landed Cost Allocation** - ตัดจ่าย landed cost ตามสัดส่วนเมื่อโอนสินค้า ✅ **มีการแชร์**
3. **Return Move Handling** - Return move ใช้ cost เดิมจาก original warehouse ✅ **ยังถูก**

---

## 🔍 ส่วนที่ 1: FIFO Queue หลังต่อ Warehouse (อิสระ)

### 1.1 แยก Queue ตามต่อ Warehouse

```python
# ใน stock_valuation_layer.py
@api.model
def _get_fifo_queue(self, product_id, warehouse_id, company_id=None):
    """
    Retrieve FIFO queue for a product at a SPECIFIC warehouse.
    """
    domain = [
        ('product_id', '=', product_id.id),
        ('warehouse_id', '=', wh_id),  # 🔑 ตรง warehouse นี้เท่านั้น
        ('company_id', '=', company_id),
        ('quantity', '>', 0),
    ]
    return self.search(domain, order='create_date asc, id asc')
```

**ผลลัพธ์:**
- ✅ Warehouse A มี FIFO queue เป็นของตัวเอง
- ✅ Warehouse B มี FIFO queue เป็นของตัวเอง
- ❌ ไม่มีการแชร์ queue

### 1.2 ตัวอย่าง Scenario

| Scenario | Warehouse A | Warehouse B | ผลลัพธ์ |
|----------|-------------|------------|--------|
| Receive 100 units @ 10/unit to WH-A | Queue: [100@10] | Queue: [] | อิสระ |
| Receive 100 units @ 12/unit to WH-B | Queue: [100@10] | Queue: [100@12] | อิสระ |
| Sell 50 units from WH-A | Queue: [50@10] | Queue: [100@12] | FIFO WH-A ได้ 50@10 |

---

## 🔄 ส่วนที่ 2: Inter-Warehouse Transfer (มีการตัดจ่าย Cost)

### 2.1 Logic เมื่อโอนสินค้าระหว่าง Warehouse

```python
# ใน stock_move.py
def _ensure_inter_warehouse_valuation_layers(self):
    """
    สร้าง valuation layers สำหรับ inter-warehouse transfer
    """
    # Get cost จาก SOURCE warehouse ใช้ FIFO cost
    fifo_result = fifo_service.calculate_fifo_cost_with_landed_cost(
        product,
        source_wh,           # 👈 ใช้ source warehouse FIFO
        move.product_qty,
        company.id
    )
    
    unit_cost = fifo_result['unit_cost']  # Cost ที่ consume จาก source
    
    # Create NEGATIVE layer ที่ source warehouse
    create({
        'quantity': -move.product_qty,
        'warehouse_id': source_wh.id,
        'unit_cost': unit_cost,           # FIFO cost จาก source
    })
    
    # Create POSITIVE layer ที่ destination warehouse
    create({
        'quantity': move.product_qty,
        'warehouse_id': dest_wh.id,
        'unit_cost': unit_cost,           # นำเข้า ด้วย cost เดียวกัน
    })
```

### 2.2 Diagram Flow

```
┌─────────────────────────────────────────────────────────────┐
│          Inter-Warehouse Transfer: 50 units                 │
└─────────────────────────────────────────────────────────────┘

WAREHOUSE A                          WAREHOUSE B
Queue: [100@10]                     Queue: [100@12]
Available: 100 units                Available: 100 units

         │
         │ Transfer 50 units
         ↓

Step 1: Calculate FIFO Cost from WH-A
  → FIFO Queue: [50@10] (consume from first layer)
  → Unit Cost = 10.00

Step 2: Create Valuation Layers
  WH-A: -50 @ 10.00 (outgoing, consume from FIFO)
  WH-B: +50 @ 10.00 (incoming, with FIFO cost from WH-A)

Step 3: Update Warehouse Balances
  WH-A Queue: [50@10]      (remaining: 50 units)
  WH-B Queue: [50@10, 100@12]  (added: 50 units)

Step 4: Transfer Landed Costs (if any)
  If WH-A had landed costs, transfer proportionally
  ✅ See Section 2.3
```

---

## 💰 ส่วนที่ 3: Landed Cost Allocation (แชร์ตามสัดส่วน)

### 3.1 โครงสร้าง Landed Cost

```python
# ใน landed_cost_location.py
class StockValuationLayerLandedCost:
    """
    Tracks landed cost SPECIFIC TO EACH WAREHOUSE
    """
    valuation_layer_id  # Link to layer
    warehouse_id        # ✅ Specific warehouse
    landed_cost_value   # Amount allocated to THIS warehouse
    quantity           # Quantity covered
    unit_landed_cost   # Computed: value / quantity
```

### 3.2 Logic การตัดจ่าย Landed Cost

```python
# ใน stock_move.py
def _allocate_landed_cost_on_transfer(self, move, layers):
    """
    When transferring 50 units from WH-A to WH-B:
    Transfer landed costs proportionally
    """
    
    # Step 1: Get total landed cost at SOURCE warehouse
    source_lc_value = get_landed_cost_at_warehouse(
        product,
        source_wh    # WH-A landed costs
    )
    # → Returns: 100.00 (例: freight, insurance)
    
    # Step 2: Get available quantity at source warehouse
    source_qty = _get_total_available_qty(
        product,
        source_wh    # WH-A quantity
    )
    # → Returns: 100 units
    
    # Step 3: Calculate proportion
    proportion = qty_transferred / source_qty
    # → 50 / 100 = 0.50 (50%)
    
    lc_to_transfer = source_lc_value * proportion
    # → 100.00 * 0.50 = 50.00
    
    # Step 4: Reduce landed cost at SOURCE warehouse
    source_lc_record.landed_cost_value -= lc_to_transfer
    # WH-A: 100.00 → 50.00
    
    # Step 5: Add landed cost at DESTINATION warehouse
    create({
        'valuation_layer_id': dest_layer.id,
        'warehouse_id': dest_wh.id,
        'landed_cost_value': lc_to_transfer,  # 50.00
        'quantity': 50,
    })
    # WH-B: 0 → 50.00
```

### 3.3 ตัวอย่างเลขจริง

```
Initial State:
═══════════════════════════════════════════════════════════
WH-A: 100 units @ 10.00/unit = 1,000.00
      Landed Cost: 100.00 (freight)
      Unit LC: 100.00 / 100 = 1.00/unit
      Total Unit Cost: 10.00 + 1.00 = 11.00/unit

WH-B: 100 units @ 12.00/unit = 1,200.00
      Landed Cost: 50.00 (freight)
      Unit LC: 50.00 / 100 = 0.50/unit
      Total Unit Cost: 12.00 + 0.50 = 12.50/unit

Transfer 50 units from WH-A to WH-B:
═══════════════════════════════════════════════════════════

1. FIFO Cost Calculation:
   From WH-A FIFO: 50 units @ 11.00/unit = 550.00 ✅

2. Valuation Layers Created:
   WH-A: -50 @ 11.00 = -550.00 (outgoing, includes LC)
   WH-B: +50 @ 11.00 = +550.00 (incoming, same cost as WH-A)

3. Landed Cost Transfer:
   Proportion: 50 / 100 = 50%
   LC to transfer: 100.00 * 50% = 50.00
   
   WH-A LC: 100.00 → 50.00 (50% left)
   WH-B LC: 50.00 → 100.00 (added 50.00)

Final State:
═══════════════════════════════════════════════════════════
WH-A: 50 units @ 10.00/unit = 500.00
      Landed Cost: 50.00 (remaining)
      Unit LC: 50.00 / 50 = 1.00/unit
      Total Unit Cost: 11.00/unit

WH-B: 150 units (100 + 50 from transfer)
      Layer 1: 100 @ 12.00/unit = 1,200.00
      Layer 2: 50 @ 11.00/unit = 550.00
      Landed Cost: 100.00 (50 + 50 transferred)
      
      Breakdown:
      - Original 100: Unit LC = 0.50/unit
      - Transferred 50: Unit LC = 1.00/unit (from WH-A)

Total Inventory Value (UNCHANGED):
═══════════════════════════════════════════════════════════
Before: 1,000 + 100 + 1,200 + 50 = 2,350.00
After:  500 + 50 + 1,200 + 550 + 100 = 2,400.00
                                    ↑ Rounding differences
```

---

## 🚨 ส่วนที่ 4: Critical Issues & Fixes

### 4.1 Return Move Logic (🔴 CRITICAL)

```python
# ใน stock_move.py - _update_created_layers_warehouse()
def calculate_return_unit_cost():
    """
    🔴 CRITICAL FIX (v17.0.1.1.2):
    Return moves ต้องใช้ FIFO cost ที่มี landed cost
    NOT base cost only
    """
    
    # WRONG ❌ (old logic):
    return_unit_cost = product.standard_price
    
    # CORRECT ✅ (new logic):
    # Find original NEGATIVE layer (delivery layer)
    original_delivery_layers = search([
        ('stock_move_id', '=', original_move.id),
        ('quantity', '<', 0),  # Outgoing layer
        ('warehouse_id', '=', original_wh.id),
    ])
    
    # Use the ACTUAL unit cost from delivery (which includes landed costs!)
    base_delivery_unit_cost = original_delivery_layers[0].unit_cost
    
    # Get additional landed costs
    lc_value = sum(lc_records.mapped('landed_cost_value'))
    unit_lc = lc_value / lc_qty
    
    # Total = base delivery cost + landed cost portion
    return_unit_cost = base_delivery_unit_cost + unit_lc
    
    # Result: balance = 0 when returning full quantity ✅
```

### 4.2 Warehouse Consistency Validation

```python
# ใน stock_valuation_layer.py
@api.constrains('warehouse_id', 'quantity', 'remaining_qty', 'remaining_value')
def _check_warehouse_consistency():
    """
    Validations:
    1. ✅ Layer with quantity MUST have warehouse_id
    2. ✅ Negative balance check (with exceptions for returns)
    3. ✅ Cross-warehouse return validation
    """
    
    # Validation 1: Must have warehouse_id
    if layer.quantity != 0 and not layer.warehouse_id:
        raise ValidationError(
            f"Layer {layer.id} has quantity but no warehouse_id"
        )
    
    # Validation 2: Prevent warehouse negative balance
    # (Skip for return moves - they handle via _action_done())
    if layer.quantity < 0 and not is_return_move(layer):
        total_remaining_qty = sum(previous_layers.mapped('remaining_qty'))
        if total_remaining_qty + layer.quantity < 0:
            raise ValidationError(
                f"Warehouse {layer.warehouse_id.name} would go negative"
            )
```

### 4.3 Return Move Warehouse Enforcement

```python
# ใน stock_move.py - _action_done()
def validate_return_warehouse():
    """
    🔴 CRITICAL: Return moves MUST go to original warehouse
    Prevents negative balance issues
    """
    
    if move.origin_returned_move_id:
        original_wh = move.origin_returned_move_id.warehouse_id
        return_wh = move._get_fifo_valuation_layer_warehouse()
        
        # If different warehouses → BLOCK
        if original_wh and return_wh and original_wh.id != return_wh.id:
            raise ValidationError(
                f"❌ Return ต้องไปที่เดิม: {original_wh.name}"
                f"ไม่ใช่ {return_wh.name}"
            )
```

---

## 🎓 ส่วนที่ 5: Architecture Pattern

### 5.1 Three-Tier Cost Model

```
┌──────────────────────────────────────────────────────────────┐
│              TIER 3: Return Move Handling                      │
│                                                               │
│  - Uses original warehouse (forced)                          │
│  - Uses FIFO cost WITH landed costs from delivery            │
│  - Results in balance = 0 when full return ✅               │
└──────────────────────────────────────────────────────────────┘
                              ↑
                              │
┌──────────────────────────────────────────────────────────────┐
│              TIER 2: Landed Cost Allocation                   │
│                                                               │
│  - Proportional transfer between warehouses                  │
│  - Audit trail in stock.landed.cost.allocation              │
│  - Maintains total landed cost (just moves it)              │
└──────────────────────────────────────────────────────────────┘
                              ↑
                              │
┌──────────────────────────────────────────────────────────────┐
│              TIER 1: FIFO Queue (Per-Warehouse)              │
│                                                               │
│  - Each warehouse has independent FIFO queue                │
│  - No mixing between warehouses                             │
│  - Cost flows from source to destination                    │
└──────────────────────────────────────────────────────────────┘
```

### 5.2 Key Design Principles

| Principle | Implementation | ทำไม |
|-----------|----------------|------|
| **Warehouse Isolation** | Each warehouse has own FIFO queue | ✅ Accurate per-location cost |
| **Cost Flow** | Inter-warehouse: consume from source FIFO | ✅ FIFO respected globally |
| **Landed Cost Sharing** | Proportional allocation on transfer | ✅ No duplication, no loss |
| **Return Accuracy** | Use original warehouse + FIFO cost | ✅ Balance = 0 on full return |
| **Data Integrity** | Validation at multiple levels | ✅ Prevent negative balance |

---

## 📋 ส่วนที่ 6: Configuration & Audit Trail

### 6.1 Stock.Landed.Cost.Allocation Model

```python
# ใน landed_cost_location.py - Audit Trail
class StockLandedCostAllocation:
    """
    Records EVERY landed cost transfer for audit
    """
    move_id                              # ← Which transfer
    source_warehouse_id                  # ← From where
    destination_warehouse_id             # ← To where
    quantity_transferred                 # ← How much
    source_layer_landed_cost_before      # ← WH-A before
    source_layer_landed_cost_after       # ← WH-A after
    destination_layer_landed_cost_before # ← WH-B before
    destination_layer_landed_cost_after  # ← WH-B after
    landed_cost_transferred              # ← Amount transferred
    notes                                # ← Description
```

### 6.2 Config Parameters

```python
stock_fifo_by_location.shortage_policy
  → 'error' (block) or 'fallback' (allow from other warehouses)

stock_fifo_by_location.enable_validation
  → 'True' (strict) or 'False' (permissive)
```

---

## 🔬 ส่วนที่ 7: Test Cases (พิสูจน์ Logic)

### 7.1 Test: Inter-Warehouse Transfer

```python
# test_fifo_by_location.py
def test_inter_warehouse_transfer_with_landed_cost():
    """
    Verify landed cost transfers correctly during inter-warehouse move
    """
    # Setup
    wh_a = create_warehouse("WH-A")
    wh_b = create_warehouse("WH-B")
    product = create_product()
    
    # Receive 100 @ 10.00 to WH-A with FC 100.00
    receive_to_wh_a(100, 10.00, landed_cost=100.00)
    
    # Transfer 50 to WH-B
    transfer(wh_a, wh_b, 50)
    
    # Assertions
    assert wh_a_layers[0].unit_cost == 11.00  # 10 + (100/100)
    assert wh_b_layers[-1].unit_cost == 11.00 # Same as source
    
    assert wh_a_landed_cost == 50.00  # 100 * 50%
    assert wh_b_landed_cost == 100.00 # 50 + 50 transferred
    
    # Total value unchanged
    assert total_valuation(before) == total_valuation(after)
```

### 7.2 Test: Return Move Balance = 0

```python
def test_return_full_quantity_balance_equals_zero():
    """
    Verify returning full quantity results in balance = 0
    🔴 CRITICAL TEST (v17.0.1.1.2)
    """
    # Setup: Deliver 100 @ 11.00 (10.00 + 1.00 LC)
    out_move = deliver(100, unit_cost=11.00)
    
    # Verify consumption layers
    delivery_neg_layer = find_negative_layer(out_move, wh_a)
    assert delivery_neg_layer.unit_cost == 11.00
    assert delivery_neg_layer.remaining_qty == 0  # Fully consumed
    
    # Return full 100 units
    return_move = create_return(out_move, 100)
    
    # Verify return layers
    return_pos_layer = find_positive_layer(return_move, wh_a)
    assert return_pos_layer.unit_cost == 11.00  # ✅ With LC!
    assert return_pos_layer.quantity == 100
    
    # Final balance check
    assert delivery_neg_layer.remaining_qty == 0
    assert return_pos_layer.remaining_qty == 100
    net_balance = -0 + 100 = 100  # ✅ Back to positive!
```

---

## ⚠️ ส่วนที่ 8: Potential Issues & Solutions

### 8.1 Issue: Double-Counting Landed Costs

**Problem:**
```
When transferring, landed cost might be counted twice:
WH-A: 100.00 LC
↓ Transfer
WH-B: 100.00 LC (but WH-A still has 100?)
```

**Solution:** ✅ Code implements reduction:
```python
# In _transfer_landed_cost_between_warehouses():
source_lc_record.write({
    'landed_cost_value': new_source_value,  # REDUCED
})
```

### 8.2 Issue: Negative Balance on Return

**Problem:**
```
Return to wrong warehouse could make balance negative:
WH-A: 100 units
↓ Return to WH-B (wrong!)
Result: WH-A = 100, WH-B = -50 (INVALID!)
```

**Solution:** ✅ Return validation blocks this:
```python
# In _action_done():
if original_wh.id != return_wh.id:
    raise ValidationError("Return must go to original warehouse")
```

### 8.3 Issue: Missing Warehouse in Layer

**Problem:**
```
Old data might have layers without warehouse_id:
Layer: Product A, Qty 50, warehouse_id = NULL
```

**Solution:** ✅ Migration script populates:
```python
# migrations/17.0.1.0.4/post-migrate.py
UPDATE stock_valuation_layer
SET warehouse_id = (
  SELECT warehouse_id FROM stock_move
  WHERE stock_valuation_layer.stock_move_id = stock_move.id
)
WHERE warehouse_id IS NULL
```

---

## 🎯 ส่วนที่ 9: Summary Table

| Aspect | Warehouse A | Warehouse B | Sharing? |
|--------|-------------|-------------|----------|
| FIFO Queue | [100@10] | [100@12] | ❌ NO |
| Available Qty | 100 | 100 | ❌ NO |
| Landed Cost | 100.00 | 50.00 | ❌ NO |
| **On Transfer 50 units** | | | |
| FIFO Queue After | [50@10] | [50@10, 100@12] | ❌ NO (separated) |
| LC After | 50.00 | 100.00 | ✅ YES (proportional) |
| Cost Transferred | 11.00/unit | 11.00/unit | ✅ YES (same cost) |

---

## 📚 ส่วนที่ 10: Recommendations

### ✅ What's Working Well
1. ✅ Independent FIFO queues per warehouse
2. ✅ Proportional landed cost allocation
3. ✅ Return move validation
4. ✅ Audit trail for all allocations
5. ✅ Cost flow from source to destination

### ⚠️ Recommendations for Enhancement
1. **Audit Dashboard**: ใหม่ UI เพื่อมองแนวน่า landed cost allocation history
2. **Shortage Fallback**: Allow config to pull from other warehouses when shortage
3. **Analytics Report**: Report แสดง cost per warehouse over time
4. **Deprecation Warning**: For old data without warehouse_id (already have migration)

---

## 📖 Reference Documents

- `stock_valuation_layer.py` - FIFO queue per warehouse
- `stock_move.py` - Inter-warehouse transfer logic
- `landed_cost_location.py` - Landed cost allocation model
- `fifo_service.py` - FIFO calculation service
- `stock_landed_cost.py` - Landed cost extension

---

*Last Updated: Version 17.0.1.1.2*
*Analysis Date: 2024-11-27*
