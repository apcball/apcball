# Inventory Adjustment Feature - Implementation Guide

## Module Version: 17.0.1.1.7

---

## Overview

The warehouse-aware inventory adjustment feature extends `stock_fifo_by_location` to support inventory adjustments that respect warehouse boundaries and provide flexible cost calculation options.

### Key Features

1. **Warehouse-Specific Inventory Adjustments**: Adjustments are tracked per warehouse
2. **Flexible Cost Rules for Increases**: Choose from standard price, last purchase price, or manual cost
3. **Warehouse-Aware FIFO for Decreases**: Automatically consumes stock from the correct warehouse using FIFO
4. **Accurate Valuation**: Creates proper stock valuation layers with correct warehouse_id

---

## Cost Rules for Stock Increases

When inventory count is **increased** (actual > system), you can choose how to value the new stock:

### 1. Standard Price (default)

Uses the product's standard price defined in the product form.

**Example:**
- Product standard price: $100
- Increase: +10 units
- **Result**: SVL created with $100/unit = $1,000 total value

**When to use:**
- Default option
- When standard costing is your primary method
- For initial stock setup

### 2. Last Purchase Price

Uses the most recent purchase price **from the specific warehouse**.

**Example:**
- Last receipt to WH-A: 5 units at $120/unit
- Adjustment at WH-A: +10 units
- **Result**: SVL created with $120/unit = $1,200 total value

**When to use:**
- Want to reflect current market prices
- Have recent purchase history
- Different warehouses have different purchase costs

**Fallback:** If no purchase history exists for the warehouse, falls back to standard price.

### 3. Manual Cost

Enter a specific unit cost manually.

**Example:**
- Manual cost entered: $150
- Increase: +10 units
- **Result**: SVL created with $150/unit = $1,500 total value

**When to use:**
- Physical count reveals damaged/discounted stock
- Special valuation circumstances
- Adjustment from known external cost source

**Validation:** Manual cost must be greater than zero.

---

## FIFO Consumption for Stock Decreases

When inventory count is **decreased** (actual < system), the system automatically uses the warehouse-aware `_run_fifo()` method to consume stock.

### How It Works

1. System identifies the warehouse from the adjustment location
2. Calls `_run_fifo()` with warehouse context
3. Consumes stock layers **only from that warehouse** in FIFO order
4. Creates negative SVL with consumed cost

### Example Scenario

**Setup:**
- WH-A has two layers:
  - Layer 1: 10 units at $100/unit (older)
  - Layer 2: 10 units at $150/unit (newer)

**Adjustment:**
- Decrease inventory by 5 units at WH-A

**Result:**
- Consumes 5 units from Layer 1 (FIFO - oldest first)
- Negative SVL: -5 units at $100/unit = -$500
- Layer 1 remaining: 5 units
- Layer 2 untouched: 10 units

**Warehouse Isolation:**
- Layers from other warehouses are **never consumed**
- Each warehouse maintains independent FIFO queues

---

## Technical Implementation

### Model Extensions

#### `stock.quant`

**New Fields:**
```python
inventory_cost_rule = fields.Selection([
    ('standard', 'Standard Price'),
    ('last_purchase', 'Last Purchase Price (This Warehouse)'),
    ('manual', 'Manual Cost'),
], string='Inventory Cost Rule', default='standard')

inventory_manual_cost = fields.Float(
    string='Manual Unit Cost',
    digits='Product Price'
)
```

**Key Methods:**
- `_apply_inventory()`: Validates cost rules, passes them via context
- `_get_inventory_cost_for_increase()`: Calculates unit cost based on selected rule
- `_get_inventory_move_values()`: Injects warehouse_id into inventory moves

#### `stock.move`

**New Field:**
```python
warehouse_id = fields.Many2one(
    'stock.warehouse',
    string='Warehouse',
    compute='_compute_warehouse_id',
    store=True
)
```

**Overridden Methods:**
- `_create_in_svl()`: Uses custom cost from inventory adjustment
- `_create_out_svl()`: Ensures warehouse context for FIFO consumption

### Context Flow

```
stock.quant._apply_inventory()
    ↓
    [validates cost rules]
    ↓
    [stores rules in context: inventory_cost_rules]
    ↓
stock.move creation
    ↓
    [warehouse_id field populated]
    ↓
stock.move._create_in_svl() (for increases)
    ↓
    [reads cost from context via quant._get_inventory_cost_for_increase()]
    ↓
stock.valuation.layer created with:
    - correct unit_cost
    - correct warehouse_id
    
OR

stock.move._create_out_svl() (for decreases)
    ↓
    [ensures warehouse in context]
    ↓
stock.move._run_fifo(warehouse_id=X)
    ↓
    [consumes layers only from warehouse X]
    ↓
stock.valuation.layer created (negative)
```

---

## User Interface

### Inventory Adjustment Form

When creating an inventory adjustment, you'll see:

**Cost Configuration Section** (for stock increases):
```
┌─────────────────────────────────────────┐
│ Cost Configuration (for increases)      │
├─────────────────────────────────────────┤
│ Cost Rule: [Standard Price       ▼]    │
│ Manual Unit Cost: [         ]           │
└─────────────────────────────────────────┘
```

**Cost Rule Options:**
1. **Standard Price**: Uses product.standard_price
2. **Last Purchase Price (This Warehouse)**: Uses most recent purchase at this warehouse
3. **Manual Cost**: Enables "Manual Unit Cost" field for input

### Inventory Line Form

Each inventory line shows:
- Product
- Location
- Current Quantity
- Counted Quantity
- **Cost Rule** (if applicable)
- **Manual Unit Cost** (if rule = manual)

---

## Usage Examples

### Example 1: Physical Count with Standard Price

**Scenario:** Found 10 extra units during physical count.

**Steps:**
1. Open inventory adjustment for location WH-A/Stock
2. Count 10 units (system shows 0)
3. Leave cost rule as "Standard Price"
4. Validate adjustment

**Result:**
- +10 units in stock
- SVL: +10 units @ standard price

### Example 2: Count with Last Purchase Price

**Scenario:** Warehouse B received goods last week at $120/unit, now doing inventory count.

**Steps:**
1. Open inventory adjustment for WH-B/Stock
2. Count 25 units (system shows 20)
3. Set cost rule to "Last Purchase Price (This Warehouse)"
4. Validate adjustment

**Result:**
- +5 units in stock
- SVL: +5 units @ $120/unit (from last receipt)

### Example 3: Damaged Goods - Manual Cost

**Scenario:** Found 8 units of damaged stock worth only $50/unit instead of standard $100.

**Steps:**
1. Open inventory adjustment
2. Count 8 units (system shows 0)
3. Set cost rule to "Manual Cost"
4. Enter manual unit cost: $50
5. Validate adjustment

**Result:**
- +8 units in stock
- SVL: +8 units @ $50/unit = $400

### Example 4: Stock Decrease

**Scenario:** System shows 20 units but physical count finds only 15 units.

**Steps:**
1. Open inventory adjustment for WH-A/Stock
2. Count 15 units (system shows 20)
3. Validate adjustment

**System Behavior:**
- Automatically runs `_run_fifo()` for WH-A
- Consumes oldest 5 units from WH-A layers
- Creates negative SVL with FIFO cost

**Result:**
- -5 units in stock
- SVL: -5 units @ cost from oldest WH-A layer

---

## Validation Rules

### Cost Rule Validation

1. **Manual Cost Required**: If cost rule is "manual", manual_cost must be > 0
2. **Warehouse Required for Last Purchase**: Location must belong to a warehouse
3. **Positive Quantities Only**: Adjustment quantities must be positive (system handles increases/decreases automatically)

### Warehouse Validation

1. **Location Must Have Warehouse**: Inventory location must be linked to a warehouse
2. **Warehouse Boundary Enforcement**: Decreases only consume from the specified warehouse

---

## Database Schema Changes

### New Fields

**stock_quant:**
```sql
ALTER TABLE stock_quant 
ADD COLUMN inventory_cost_rule VARCHAR;

ALTER TABLE stock_quant 
ADD COLUMN inventory_manual_cost NUMERIC;
```

**stock_move:**
```sql
ALTER TABLE stock_move 
ADD COLUMN warehouse_id INTEGER 
REFERENCES stock_warehouse(id);
```

### Indexes

Recommended indexes for performance:
```sql
CREATE INDEX idx_stock_valuation_layer_warehouse_product 
ON stock_valuation_layer(warehouse_id, product_id, create_date);

CREATE INDEX idx_stock_move_warehouse 
ON stock_move(warehouse_id);
```

---

## Testing

### Test Coverage

The module includes comprehensive tests in `tests/test_inventory_adjustment.py`:

1. **test_inventory_adjustment_increase_standard_price**: Verifies standard price cost rule
2. **test_inventory_adjustment_increase_manual_cost**: Verifies manual cost entry
3. **test_inventory_adjustment_increase_last_purchase_price**: Verifies warehouse-specific last purchase
4. **test_inventory_adjustment_decrease_uses_fifo**: Verifies FIFO consumption on decreases
5. **test_inventory_adjustment_warehouse_isolation**: Verifies warehouse boundaries
6. **test_manual_cost_required_validation**: Verifies validation rules

### Running Tests

```bash
# Run all inventory adjustment tests
python odoo-bin -c odoo.conf -d your_database \
  -i stock_fifo_by_location \
  --test-enable \
  --test-tags /stock_fifo_by_location:TestInventoryAdjustmentWarehouse \
  --stop-after-init

# Run specific test
python odoo-bin -c odoo.conf -d your_database \
  --test-enable \
  --test-tags /stock_fifo_by_location:TestInventoryAdjustmentWarehouse.test_inventory_adjustment_increase_standard_price \
  --stop-after-init
```

---

## Integration with Existing Modules

### Dependencies

- **stock**: Core inventory module
- **stock_account**: For valuation layers
- **stock_inventory_ajustement**: (If installed) - Our views extend this module's views

### Compatibility

- ✅ Compatible with `stock_inventory_ajustement` module
- ✅ Compatible with standard Odoo inventory adjustments
- ✅ Compatible with landed costs
- ✅ Compatible with inter-warehouse transfers

---

## Troubleshooting

### Issue: Manual cost field not showing

**Solution:** Ensure cost rule is set to "Manual Cost"

### Issue: Last purchase price returns standard price

**Cause:** No purchase history for this warehouse  
**Solution:** Expected behavior - fallback to standard price. Check logs for warning message.

### Issue: Decrease uses wrong cost

**Cause:** Layers from wrong warehouse might be in database without warehouse_id  
**Solution:** Run layer repair script to populate warehouse_id on historical layers

### Issue: Validation error "Manual cost must be greater than zero"

**Cause:** Manual cost rule selected but no cost entered  
**Solution:** Enter a valid unit cost > 0 or change cost rule

---

## Performance Considerations

### Query Optimization

1. **Last Purchase Price Lookup**: Indexed query on `stock_valuation_layer`
2. **FIFO Consumption**: Uses existing warehouse_id index
3. **Batch Adjustments**: Process large adjustments in smaller batches

### Best Practices

1. Set cost rules before mass adjustments
2. Use "Standard Price" for routine adjustments (fastest)
3. Use "Last Purchase" only when needed (requires database lookup)
4. Avoid manual cost on large batches (requires user input per line)

---

## Migration from Previous Versions

### From 17.0.1.1.6 → 17.0.1.1.7

**Database Changes:**
- New fields added to stock_quant (inventory_cost_rule, inventory_manual_cost)
- New field added to stock_move (warehouse_id)

**Migration Steps:**
1. Upgrade module: `odoo-bin -u stock_fifo_by_location`
2. No data migration needed (new fields have defaults)
3. Test inventory adjustment on non-production environment
4. Deploy to production

**Backward Compatibility:**
- ✅ Existing layers remain unchanged
- ✅ Existing moves work normally
- ✅ Default cost rule is "standard" (previous behavior)

---

## API Reference

### Python API

#### Create Inventory Adjustment with Cost Rule

```python
# Get quant
quant = env['stock.quant'].search([
    ('product_id', '=', product_id),
    ('location_id', '=', location_id),
], limit=1)

# Set inventory quantity and cost rule
quant.write({
    'inventory_quantity': 100,
    'inventory_cost_rule': 'manual',
    'inventory_manual_cost': 150.0,
})

# Apply adjustment
quant.action_apply_inventory()
```

#### Calculate Cost for Increase

```python
quant = env['stock.quant'].browse(quant_id)
warehouse = env['stock.warehouse'].browse(warehouse_id)

cost = quant._get_inventory_cost_for_increase(warehouse=warehouse)
```

---

## Related Documentation

- [STOCK_FIFO_BY_LOCATION_FIX_v17.0.1.1.5.md](STOCK_FIFO_BY_LOCATION_FIX_v17.0.1.1.5.md) - Core FIFO by location
- [CROSS_WAREHOUSE_RETURN_IMPLEMENTATION_GUIDE.md](CROSS_WAREHOUSE_RETURN_IMPLEMENTATION_GUIDE.md) - Cross-warehouse returns
- [00_START_HERE_INVESTIGATION_SUMMARY.md](00_START_HERE_INVESTIGATION_SUMMARY.md) - Overall project context

---

## Support & Contributions

For issues or questions:
1. Check test cases in `tests/test_inventory_adjustment.py`
2. Review implementation in `models/stock_quant.py`
3. Check logs for warning/error messages

---

**Version:** 17.0.1.1.7  
**Last Updated:** 2024  
**Module:** stock_fifo_by_location
