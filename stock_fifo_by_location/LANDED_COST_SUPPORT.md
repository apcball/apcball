# Stock FIFO by Location - Landed Cost Support

## 📋 Overview

This document describes the landed cost support feature in the `stock_fifo_by_location` module. The module now tracks and allocates landed costs on a per-location basis, ensuring that when inventory is transferred between locations, the associated landed costs are proportionally transferred as well.

## 🎯 Problem Statement

When using multi-warehouse environments with Odoo's stock landed cost feature:
- Landed costs are applied to incoming stock
- During internal transfers between locations, the original landed cost information is not tracked
- This leads to inaccurate cost calculations when inventory is moved between warehouses

**Example:**
```
Location A receives 100 units @ $100/unit with $50 landed cost
Location A FIFO cost: $100 + ($50/100 units) = $100.50 per unit

Transfer 50 units from Location A to Location B
Location B should receive inventory with proper landed cost allocation
```

## ✨ Solution: Per-Location Landed Cost Tracking

The module introduces automatic landing cost allocation during internal transfers:

### New Models

#### 1. `stock.valuation.layer.landed.cost`
Tracks landed costs on a per-location basis.

**Fields:**
- `valuation_layer_id` - Reference to the stock.valuation.layer
- `location_id` - The specific location where this cost applies
- `landed_cost_id` - Source landed cost document
- `landed_cost_value` - Amount of landed cost (in company currency)
- `quantity` - Quantity this landed cost covers
- `unit_landed_cost` - Computed field: landed_cost_value / quantity

**Purpose:** Maintains a detailed audit trail of how landed costs are distributed across locations.

#### 2. `stock.landed.cost.allocation`
Tracks the history of landed cost allocation during transfers.

**Fields:**
- `move_id` - The stock move that triggered the allocation
- `product_id` - Product being transferred (related from move)
- `source_location_id` - Source location (related from move)
- `destination_location_id` - Destination location (related from move)
- `quantity_transferred` - How much was transferred
- `source_layer_landed_cost_before/after` - LC value before and after transfer
- `destination_layer_landed_cost_before/after` - LC value before and after transfer
- `landed_cost_transferred` - Amount of LC that moved to destination
- `notes` - Additional details

**Purpose:** Creates an audit trail showing exactly how landed costs were allocated during each transfer.

### Enhanced Models

#### 3. `stock.valuation.layer` (Enhanced)
Added fields and methods:

**New Fields:**
```python
landed_cost_ids = fields.One2many(
    'stock.valuation.layer.landed.cost',
    'valuation_layer_id',
)

total_landed_cost = fields.Float(
    compute='_compute_total_landed_cost',
)
```

**New Methods:**
```python
get_landed_cost_at_location(product_id, location_id, company_id)
    → Returns total landed cost for product at location

_compute_total_landed_cost()
    → Sums all landed costs across locations for this layer
```

#### 4. `stock.landed.cost` (Enhanced)
Modified to support per-location allocation.

**New Methods:**
```python
_allocate_landed_costs_by_location()
    → Creates stock.valuation.layer.landed.cost records after validation
    
button_validate()
    → Override to call _allocate_landed_costs_by_location after parent
```

#### 5. `stock.move` (Enhanced)
Added methods to handle landed cost transfer during internal moves.

**New Methods:**
```python
_allocate_landed_cost_on_transfer(move, layers)
    → Allocate landed costs proportionally during transfer
    
_transfer_landed_cost_between_locations(...)
    → Move landed cost records from source to destination location
```

## 🔄 Process Flow

### Step 1: Receiving Goods with Landed Cost

```
Purchase Order → Stock Receipt (Location A, 100 units @ $100)
    ↓
stock.valuation.layer created (qty=100, location_id=A, unit_cost=$100)
    ↓
Landed Cost Applied ($50)
    ↓
stock.valuation.layer.landed.cost created:
    valuation_layer_id = layer from step 1
    location_id = A
    landed_cost_value = $50
    unit_landed_cost = $50/100 = $0.50
    
Result: Location A has inventory @ $100.50 per unit
```

### Step 2: Internal Transfer with Landed Cost Allocation

```
Internal Transfer: Location A → Location B (50 units)
    ↓
Stock move validated
    ↓
system calls _allocate_landed_cost_on_transfer()
    ↓
Calculate proportion: 50 transferred / 100 available = 50%
Calculate LC to transfer: $50 × 50% = $25
    ↓
Update stock.valuation.layer.landed.cost records:
    - Location A: landed_cost_value reduced from $50 to $25
    - Location B: new record created with landed_cost_value=$25
    ↓
Create stock.landed.cost.allocation record (audit trail)
    ↓
Result:
    Location A: 50 units @ $100.50 per unit ($25 LC)
    Location B: 50 units @ $100.50 per unit ($25 LC)
```

### Step 3: Multiple Transfers (Cascading Allocation)

```
Start:
  Location A: 100 units, $50 LC
  Location B: 0 units

Transfer 50 from A → B:
  Location A: 50 units, $25 LC ← ($50 × 50/100)
  Location B: 50 units, $25 LC ← transferred

Transfer 25 from B → C:
  Location B: 25 units, $12.50 LC ← ($25 × 25/50)
  Location C: 25 units, $12.50 LC ← transferred

Total LC accounted for: $25 + $12.50 + $12.50 = $50 ✓
```

## 📊 Data Structure

### Valuation Layer with Landed Cost

```
Stock Valuation Layer (SVL)
├── valuation_layer_ids (One2many)
│   └── stock.valuation.layer.landed.cost
│       ├── valuation_layer_id → SVL
│       ├── location_id → Location A
│       ├── landed_cost_id → LC doc
│       ├── landed_cost_value → $50
│       ├── quantity → 100
│       └── unit_landed_cost → $0.50 (computed)
└── total_landed_cost → $50 (computed)
```

### Allocation History

```
Stock Landed Cost Allocation
├── move_id → Stock Move (A→B transfer)
├── product_id → Product
├── source_location_id → Location A
├── destination_location_id → Location B
├── quantity_transferred → 50 units
├── source_layer_landed_cost_before → $50
├── source_layer_landed_cost_after → $25
├── destination_layer_landed_cost_before → $0
├── destination_layer_landed_cost_after → $25
├── landed_cost_transferred → $25
└── notes → "Automatic landed cost allocation..."
```

## 🔧 API Methods

### In `stock.valuation.layer`

```python
# Get total landed cost for a product at location
lc = svl.get_landed_cost_at_location(product, location, company)
# Returns: 50.0 (total LC at location)

# Compute total LC across all locations for a layer
layer._compute_total_landed_cost()
# Updates: layer.total_landed_cost
```

### In `fifo.service` (New Methods)

```python
# Get total landed cost at location
lc = env['fifo.service'].get_landed_cost_at_location(product, location, company)
# Returns: float

# Get unit landed cost (LC / qty)
unit_lc = env['fifo.service'].get_unit_landed_cost_at_location(product, location, company)
# Returns: float

# Calculate COGS including landed costs
cost_info = env['fifo.service'].calculate_fifo_cost_with_landed_cost(
    product, location, quantity, company
)
# Returns: {
#   'cost': 1250.0,           # Includes landed cost
#   'qty': 12.0,
#   'unit_cost': 104.17,      # With landed cost included
#   'landed_cost': 10.0,      # Landed cost portion
#   'layers': [               # Each layer includes landed cost
#     {
#       'layer_id': 123,
#       'qty_consumed': 10,
#       'cost': 1000,
#       'layer_landed_cost': 5,
#       'cost': 1005          # Including landed cost
#     }
#   ]
# }
```

## 📈 Accounting Impact

### Journal Entries

**Receiving with Landed Cost:**
```
Debit: Inventory (Location A)                 $10,050
    Credit: Accounts Payable                          $10,000
    Credit: Landed Cost Payable                       $50

After LC validation:
Debit: Inventory (Location A)                 $50
    Credit: Landed Cost Payable                       $50
```

**Internal Transfer (with LC allocation):**
```
Debit: Inventory (Location B)                 $5,025  ← Includes LC
    Credit: Inventory (Location A)                    $5,025

(Location A loses $25 LC, Location B gains $25 LC)
```

**Delivery from Location A:**
```
Debit: COGS                                   $5,025  ← Uses LC from Location A
    Credit: Inventory (Location A)                    $5,025

COGS = 50 units × $100.50 (including LC) = $5,025
```

## 🧪 Testing

### Test Cases Added

1. **test_landed_cost_at_location_creation**
   - Verify landed costs are recorded at specific location
   - Check location_id is properly set

2. **test_landed_cost_transfer_between_locations**
   - Transfer inventory between locations
   - Verify landed cost is split proportionally
   - Check totals are preserved

3. **test_landed_cost_allocation_history**
   - Verify allocation history is created
   - Check audit trail records

### Running Tests

```bash
# Run only landed cost tests
python -m odoo.bin -d your_database -m stock_fifo_by_location --test-enable \
    -x stock_fifo_by_location.tests.test_fifo_by_location.TestLandedCostByLocation

# Run all tests
python -m odoo.bin -d your_database -m stock_fifo_by_location --test-enable
```

## 🔍 Troubleshooting

### Issue: Landed Cost Not Allocated After Transfer

**Causes:**
- `stock_landed_costs` module not installed
- Landed costs not marked as "Done"
- No valuation layer at source location

**Solutions:**
```bash
# Ensure module is installed
Settings → Apps → stock_landed_costs (Install)

# Check landed cost status
account.move (LC) → state = 'posted'

# Verify allocation was created
SELECT * FROM stock_landed_cost_allocation 
WHERE move_id = <transfer_move_id>;
```

### Issue: Landed Cost Value Mismatch

**Debugging:**
```python
# Check landed costs at each location
product = env['product.product'].browse(product_id)
loc_a = env['stock.location'].browse(loc_a_id)
loc_b = env['stock.location'].browse(loc_b_id)

lc_a = env['stock.valuation.layer'].get_landed_cost_at_location(product, loc_a)
lc_b = env['stock.valuation.layer'].get_landed_cost_at_location(product, loc_b)

print(f"Location A LC: {lc_a}")
print(f"Location B LC: {lc_b}")
print(f"Total: {lc_a + lc_b}")

# Check allocation history
allocations = env['stock.landed.cost.allocation'].search([
    ('product_id', '=', product_id),
])
for alloc in allocations:
    print(f"Move {alloc.move_id.name}: {alloc.landed_cost_transferred} transferred")
```

### Issue: LC Not Transferred on Internal Move

**Check:**
1. Internal move is confirmed (state = 'done')
2. Stock.move.state is correctly set
3. `_allocate_landed_cost_on_transfer` is being called

**Enable Debug:**
```python
# Add debug logging in stock_move.py
_logger.info(f"Allocating LC for move {move.id}: {qty_transferred} units")

# Check if layers exist
layers = env['stock.valuation.layer'].search([
    ('stock_move_id', '=', move.id),
])
_logger.info(f"Found {len(layers)} layers for move")
```

## 📚 Database Queries

### View Landed Costs at Location

```sql
SELECT 
    p.name as product,
    l.name as location,
    svl.id as layer_id,
    svl.quantity,
    svlc.landed_cost_value,
    svlc.unit_landed_cost,
    svl.unit_cost + svlc.unit_landed_cost as total_unit_cost
FROM stock_valuation_layer svl
JOIN product_product p ON svl.product_id = p.id
JOIN stock_location l ON svl.location_id = l.id
LEFT JOIN stock_valuation_layer_landed_cost svlc 
    ON svl.id = svlc.valuation_layer_id AND l.id = svlc.location_id
WHERE svl.quantity > 0
ORDER BY l.name, svl.create_date;
```

### Track Landed Cost Allocation History

```sql
SELECT 
    sm.name as move_name,
    p.name as product,
    l1.name as from_location,
    l2.name as to_location,
    slca.quantity_transferred,
    slca.landed_cost_transferred,
    slca.create_date
FROM stock_landed_cost_allocation slca
JOIN stock_move sm ON slca.move_id = sm.id
JOIN product_product p ON slca.product_id = p.id
JOIN stock_location l1 ON slca.source_location_id = l1.id
JOIN stock_location l2 ON slca.destination_location_id = l2.id
ORDER BY slca.create_date DESC;
```

## 🚀 Advanced Usage

### Custom Landed Cost Allocation Logic

```python
# Extend stock.move to customize landed cost allocation
class CustomStockMove(models.Model):
    _inherit = 'stock.move'
    
    def _allocate_landed_cost_on_transfer(self, move, layers):
        """Override with custom allocation logic"""
        # Custom logic here
        return super()._allocate_landed_cost_on_transfer(move, layers)
```

### Query Effective Cost with Landed Cost

```python
product = env['product.product'].browse(product_id)
location = env['stock.location'].browse(location_id)

# Get FIFO cost including landed costs
cost_info = env['fifo.service'].calculate_fifo_cost_with_landed_cost(
    product, location, qty=10
)

print(f"Total cost: {cost_info['cost']}")
print(f"Including landed cost: {cost_info['landed_cost']}")
print(f"Unit cost (with LC): {cost_info['unit_cost']}")
```

## 📋 Configuration

Module settings in `data/config_parameters.xml`:

```xml
<!-- Existing settings continue to apply -->
<!-- stock_fifo_by_location.shortage_policy -->
<!-- stock_fifo_by_location.enable_validation -->
<!-- stock_fifo_by_location.debug_mode -->

<!-- No new settings required for landed cost support -->
<!-- (Uses existing Odoo stock landed cost configuration) -->
```

## 🎯 Key Takeaways

| Aspect | Detail |
|--------|--------|
| **Scope** | Per-location landed cost tracking and allocation |
| **Trigger** | Automatically on internal transfers |
| **Calculation** | Proportional based on qty transferred / qty available |
| **Audit Trail** | stock.landed.cost.allocation records each allocation |
| **API** | fifo.service.calculate_fifo_cost_with_landed_cost() |
| **Data Models** | +2 new, 3 enhanced |
| **Impact** | Accurate landed cost allocation across locations |

## 📝 Version Info

- **Module:** stock_fifo_by_location
- **Version:** 17.0.1.0.0 (with LC support)
- **Odoo Version:** 17
- **Dependencies:** stock, stock_account, stock_landed_costs
- **License:** LGPL-3
