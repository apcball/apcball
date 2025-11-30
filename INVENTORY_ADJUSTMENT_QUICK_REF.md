# Inventory Adjustment Quick Reference

## Version 17.0.1.1.7 - Warehouse-Aware Inventory Adjustments

---

## Quick Overview

| Feature | Description |
|---------|-------------|
| **Stock Increases** | Choose cost rule: Standard / Last Purchase / Manual |
| **Stock Decreases** | Automatic warehouse FIFO consumption |
| **Warehouse Isolation** | Each warehouse maintains separate FIFO queues |
| **Valuation Accuracy** | Proper SVL creation with correct warehouse_id |

---

## Cost Rules Comparison

| Rule | When to Use | Cost Source | Pros | Cons |
|------|-------------|-------------|------|------|
| **Standard Price** | Default, routine adjustments | `product.standard_price` | ✓ Fast<br>✓ Simple<br>✓ Consistent | ✗ May not reflect actual cost |
| **Last Purchase** | Recent price changes | Last receipt at warehouse | ✓ Current market price<br>✓ Warehouse-specific | ✗ Requires DB lookup<br>✗ Falls back if no history |
| **Manual Cost** | Special cases, damaged goods | User input | ✓ Flexible<br>✓ Handles exceptions | ✗ Requires manual entry<br>✗ User must know cost |

---

## Usage Quick Start

### Stock Increase (Count > System)

```
1. Open Inventory Adjustment
2. Select Location (e.g., WH-A/Stock)
3. Enter Counted Quantity
4. Choose Cost Rule:
   ▸ Standard Price [default]
   ▸ Last Purchase Price (This Warehouse)
   ▸ Manual Cost → Enter cost
5. Validate
```

### Stock Decrease (Count < System)

```
1. Open Inventory Adjustment
2. Select Location
3. Enter Counted Quantity (lower than system)
4. Validate
→ System automatically uses warehouse FIFO
```

---

## Examples

### Example 1: Standard Price Increase
```
Product: Widget A (standard price: $100)
Location: WH-A/Stock
System Qty: 0
Counted: 10
Cost Rule: Standard Price

Result:
✓ +10 units at WH-A
✓ SVL: +10 @ $100 = $1,000
```

### Example 2: Last Purchase Price
```
Product: Widget B
Location: WH-B/Stock
Last WH-B Receipt: $120/unit (3 days ago)
System Qty: 20
Counted: 25
Cost Rule: Last Purchase Price

Result:
✓ +5 units at WH-B
✓ SVL: +5 @ $120 = $600
```

### Example 3: Manual Cost (Damaged)
```
Product: Widget C (standard: $100)
Location: WH-A/Stock
Condition: Damaged (worth $50)
System Qty: 0
Counted: 8
Cost Rule: Manual Cost → $50

Result:
✓ +8 units at WH-A
✓ SVL: +8 @ $50 = $400
```

### Example 4: Stock Decrease with FIFO
```
Product: Widget D
Location: WH-A/Stock
WH-A Layers:
  - 10 units @ $100 (oldest)
  - 10 units @ $150 (newest)
System Qty: 20
Counted: 15

Result:
✓ -5 units from WH-A
✓ Consumed from oldest layer (FIFO)
✓ SVL: -5 @ $100 = -$500
✓ Layer 1: 5 units left @ $100
✓ Layer 2: 10 units untouched @ $150
```

---

## Validation Rules

| Rule | Error Message | Solution |
|------|---------------|----------|
| Manual cost > 0 | "Manual cost must be greater than zero" | Enter valid cost or change rule |
| Location has warehouse | "Cannot determine warehouse" | Use location inside a warehouse |
| Quantity positive | "Invalid quantity" | Enter positive number |

---

## Technical Flow

### Stock Increase Flow
```
User enters count > system
    ↓
Select cost rule
    ↓
[Standard] → Use product.standard_price
[Last Purchase] → Query last receipt SVL for warehouse
[Manual] → Use user input
    ↓
Create positive SVL with calculated cost
    ↓
Update stock quantity
```

### Stock Decrease Flow
```
User enters count < system
    ↓
System identifies warehouse from location
    ↓
Call _run_fifo(warehouse_id=X)
    ↓
Find oldest layer in warehouse X
    ↓
Consume quantity from layer (FIFO)
    ↓
Create negative SVL with consumed cost
    ↓
Update remaining_qty on layer
```

---

## Common Scenarios

### Scenario A: Initial Stock Setup
**Use:** Standard Price  
**Why:** Fast, consistent, no history needed

### Scenario B: After Recent Purchase
**Use:** Last Purchase Price  
**Why:** Reflects current cost, warehouse-specific

### Scenario C: Damaged/Special Stock
**Use:** Manual Cost  
**Why:** Need specific valuation

### Scenario D: Stock Count Shortfall
**Use:** Automatic (no choice)  
**Why:** System handles FIFO automatically

---

## Troubleshooting

| Problem | Quick Fix |
|---------|-----------|
| Manual cost field hidden | Set cost rule to "Manual Cost" |
| Last purchase returns standard | Normal - no purchase history, check logs |
| Wrong FIFO cost on decrease | Check warehouse_id on layers, may need repair |
| Can't see cost rules | Update to v17.0.1.1.7, restart Odoo |

---

## Database Fields

### stock_quant
- `inventory_cost_rule`: Selection (standard/last_purchase/manual)
- `inventory_manual_cost`: Float

### stock_move
- `warehouse_id`: Many2one to stock.warehouse

### stock_valuation_layer
- `warehouse_id`: Already exists from v17.0.1.1.0

---

## API Quick Reference

### Python - Create Adjustment with Cost Rule
```python
quant = env['stock.quant'].search([
    ('product_id', '=', product.id),
    ('location_id', '=', location.id),
], limit=1)

quant.write({
    'inventory_quantity': 100,
    'inventory_cost_rule': 'manual',
    'inventory_manual_cost': 150.0,
})

quant.action_apply_inventory()
```

### XML-RPC - Apply Adjustment
```python
models.execute_kw(db, uid, password,
    'stock.quant', 'write',
    [[quant_id], {
        'inventory_quantity': 100,
        'inventory_cost_rule': 'standard',
    }]
)

models.execute_kw(db, uid, password,
    'stock.quant', 'action_apply_inventory',
    [[quant_id]]
)
```

---

## Testing Commands

```bash
# Run all inventory adjustment tests
python odoo-bin -c odoo.conf -d test_db \
  --test-enable \
  --test-tags /stock_fifo_by_location:TestInventoryAdjustmentWarehouse \
  --stop-after-init

# Run specific test
python odoo-bin -c odoo.conf -d test_db \
  --test-enable \
  --test-tags /stock_fifo_by_location:TestInventoryAdjustmentWarehouse.test_inventory_adjustment_increase_manual_cost \
  --stop-after-init
```

---

## Performance Tips

1. **Use Standard Price for bulk**: Fastest option
2. **Batch adjustments**: Process in smaller groups
3. **Index optimization**: Ensure warehouse_id indexes exist
4. **Cache warming**: Run adjustment once after restart

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 17.0.1.1.7 | 2024 | ✓ Added inventory adjustment cost rules<br>✓ Warehouse-aware FIFO for decreases<br>✓ UI for cost selection |
| 17.0.1.1.6 | 2024 | ✓ Cross-warehouse returns |
| 17.0.1.1.5 | 2024 | ✓ Core warehouse FIFO |

---

## Related Docs

- **Full Guide**: [INVENTORY_ADJUSTMENT_IMPLEMENTATION_GUIDE.md](INVENTORY_ADJUSTMENT_IMPLEMENTATION_GUIDE.md)
- **Thai Guide**: [INVENTORY_ADJUSTMENT_TH.md](INVENTORY_ADJUSTMENT_TH.md)
- **Tests**: `tests/test_inventory_adjustment.py`
- **Code**: `models/stock_quant.py`

---

**Module:** stock_fifo_by_location  
**Version:** 17.0.1.1.7  
**Updated:** 2024
