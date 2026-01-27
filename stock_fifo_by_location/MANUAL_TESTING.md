# Manual Testing Guide for Stock FIFO by Location

This guide provides step-by-step instructions for manual testing of the stock_fifo_by_location module.

## Pre-Test Checklist

- [ ] Module installed and activated in Odoo
- [ ] Products created with FIFO costing method
- [ ] Warehouse and locations configured
- [ ] Stock and stock_account modules enabled

## Test Scenarios

### Scenario 1: Basic Incoming Receipt with Location Tracking

**Objective:** Verify that receiving goods populates location_id correctly.

**Steps:**

1. Create a Purchase Order:
   - Navigate to: **Purchases** → **Requests for Quotation** → **Create**
   - Add product with FIFO cost method
   - Quantity: 10 units
   - Unit cost: $100

2. Confirm and Receive:
   - Click **Confirm Order**
   - Click **Receive** to validate receipt picking
   - Specify destination location as **Location A**

3. Validate in Database:
   - Go to: **Inventory** → **Valuation Layers**
   - Filter by product name
   - Verify:
     - ✅ `location_id` = Location A
     - ✅ `quantity` = 10
     - ✅ `unit_cost` = 100

**Expected Result:** SVL record shows Location A with 10 units

---

### Scenario 2: FIFO Queue Isolation Per Location

**Objective:** Verify that FIFO queues are location-specific.

**Setup from Scenario 1:**
- Location A: 10 units @ $100

**Steps:**

1. Create another Purchase Order:
   - Product: Same as Scenario 1
   - Quantity: 5 units
   - Unit cost: $120
   - Destination: **Location B**

2. Verify isolation:
   - Navigate to: **Inventory** → **Valuation Layers**
   - Filter by product
   - Observe two layers:
     - Layer 1: Location A, qty 10, cost $100
     - Layer 2: Location B, qty 5, cost $120
   - Verify they do NOT mix

**Expected Result:** Two separate layers, one per location

---

### Scenario 3: FIFO Cost Calculation (Main Test)

**Objective:** Verify FIFO consumption from correct location.

**Setup:**
- Location A: Receipt 1 (qty 10 @ $100), Receipt 2 (qty 5 @ $120)

**Steps:**

1. Create Sales Order from Location A:
   - Navigate to: **Sales** → **Orders** → **Create**
   - Add product from Setup
   - Quantity: 12
   - Select delivery from **Location A**

2. Confirm and Deliver:
   - Click **Confirm**
   - Click **Deliver**
   - Validate the picking

3. Verify COGS:
   - Navigate to: **Accounting** → **Journal Entries**
   - Filter by COGS account
   - Find entry for this product
   - **Expected amount:** 10 × $100 + 2 × $120 = $1,240

4. Verify Valuation Layer Updates:
   - Navigate to: **Inventory** → **Valuation Layers**
   - Layer 1 (Location A, $100): quantity should be 0 (fully consumed)
   - Layer 2 (Location A, $120): quantity should be 3 (5 - 2 consumed)

**Expected Result:** COGS = $1,240 (FIFO consumption respected)

---

### Scenario 4: Shortage Handling - Error Mode

**Objective:** Verify module blocks delivery when insufficient stock.

**Setup:**
- Location A: 5 units
- Shortage policy: **error** (default)

**Steps:**

1. Create Sales Order:
   - Product: Same
   - Quantity: 10 (exceeds available)
   - Delivery location: **Location A**

2. Attempt to Deliver:
   - Click **Confirm** → **Deliver** → **Validate Picking**

3. Verify Error:
   - Should receive error message:
     > "Insufficient quantity for product... at location Location A. Available: 5, Needed: 10"

**Expected Result:** Delivery blocked with clear error message

---

### Scenario 5: Shortage Handling - Fallback Mode

**Objective:** Verify module identifies fallback locations.

**Setup:**
- Location A: 5 units
- Location B: 8 units
- Change shortage policy to **fallback**

**Steps:**

1. Change Configuration:
   - Navigate to: **Settings** → **Technical** → **Parameters**
   - Search for: `stock_fifo_by_location.shortage_policy`
   - Change value to: `fallback`

2. Create Sales Order from Location A:
   - Quantity: 12 (insufficient at Location A)

3. In Delivery Screen:
   - System should warn about Location A shortage
   - Suggest Location B as fallback
   - Option to pull from Location B if configured

**Expected Result:** System identifies and suggests fallback location

---

### Scenario 6: Internal Transfer (Location A → Location B)

**Objective:** Verify internal transfers maintain location tracking.

**Setup:**
- Location A: 20 units @ $100 (from earlier receipts)

**Steps:**

1. Create Internal Transfer:
   - Navigate to: **Inventory** → **Transfers** → **Create**
   - Product: Test product
   - From Location: **Location A**
   - To Location: **Location B**
   - Quantity: 12

2. Validate Transfer:
   - Click **Confirm** → **Validate**

3. Verify Results:
   - Location A: 8 units remaining
   - Location B: 12 units newly available
   - Both maintain same cost basis ($100)

**Expected Result:** Inventory transferred, location tracking updated

---

### Scenario 7: Multiple Locations with Different Costs

**Objective:** Verify costs are not mixed across locations.

**Setup:**
- Product: Widget
- Location A: 50 units @ $100 each = $5,000 total value
- Location B: 50 units @ $150 each = $7,500 total value
- Total inventory value: $12,500

**Steps:**

1. Deliver 25 units from Location A:
   - Create sales order, quantity 25
   - Delivery from Location A
   - Validate

2. Verify COGS:
   - Should be: 25 × $100 = $2,500 (NOT $2,500 + variation)

3. Deliver 25 units from Location B:
   - Create sales order, quantity 25
   - Delivery from Location B
   - Validate

4. Verify COGS:
   - Should be: 25 × $150 = $3,750 (NOT $100 cost)

5. Check Inventory Values:
   - Remaining Location A: 25 units @ $100 = $2,500
   - Remaining Location B: 25 units @ $150 = $3,750
   - Total: $6,250 (50% reduction = correct)

**Expected Result:** Each location maintains separate cost basis

---

## Python Console Testing

For advanced testing, use Odoo Python shell:

```bash
cd /path/to/odoo17
python -m odoo.bin shell -d your_database
```

### Test 1: Get FIFO Queue for Location

```python
from odoo import env

# Get product and location
product = env['product.product'].search([('name', '=', 'Test Product FIFO')], limit=1)
location_a = env['stock.location'].search([('name', '=', 'Location A')], limit=1)

# Get FIFO queue
service = env['fifo.service']
queue = service.get_valuation_layer_queue(product, location_a)

print(f"FIFO Queue for {product.name} at {location_a.name}:")
for layer in queue:
    print(f"  Layer {layer.id}: qty={layer.quantity}, cost={layer.unit_cost}, value={layer.value}")
```

### Test 2: Calculate FIFO Cost

```python
# Calculate cost for consuming 12 units from Location A
cost_info = service.calculate_fifo_cost(product, location_a, 12)

print(f"FIFO Cost Calculation:")
print(f"  Quantity to consume: 12")
print(f"  Total cost: ${cost_info['cost']:.2f}")
print(f"  Average unit cost: ${cost_info['unit_cost']:.2f}")
print(f"  Layers consumed:")
for layer_info in cost_info['layers']:
    print(f"    Layer {layer_info['layer_id']}: {layer_info['qty_consumed']} units @ ${layer_info['layer_unit_cost']:.2f} = ${layer_info['cost']:.2f}")
```

### Test 3: Validate Availability

```python
# Check availability at Location A for 30 units
result = service.validate_location_availability(product, location_a, 30, allow_fallback=False)

print(f"Availability Check:")
print(f"  Available: {result['available']}")
print(f"  Available qty: {result['available_qty']}")
print(f"  Needed: {result['needed_qty']}")
print(f"  Shortage: {result['shortage']}")
if result['fallback_locations']:
    print(f"  Fallback options: {result['fallback_locations']}")
```

### Test 4: Get Total Available Qty

```python
total_qty = service.get_available_qty_at_location(product, location_a, env.company.id)
print(f"Total available at {location_a.name}: {total_qty} units")
```

## Database Verification Queries

### Query 1: Check All Valuation Layers by Location

```sql
SELECT 
    svl.id,
    svl.create_date,
    sp.name as product,
    sl.name as location,
    svl.quantity,
    svl.unit_cost,
    svl.value
FROM stock_valuation_layer svl
LEFT JOIN product_product sp ON svl.product_id = sp.id
LEFT JOIN stock_location sl ON svl.location_id = sl.id
WHERE sp.name = 'Test Product FIFO'
ORDER BY sl.name, svl.create_date;
```

### Query 2: Verify Location Isolation

```sql
SELECT 
    svl.location_id,
    sl.name as location,
    COUNT(*) as num_layers,
    SUM(svl.quantity) as total_qty,
    SUM(svl.value) as total_value
FROM stock_valuation_layer svl
LEFT JOIN stock_location sl ON svl.location_id = sl.id
WHERE svl.product_id IN (
    SELECT id FROM product_product WHERE name = 'Test Product FIFO'
)
GROUP BY svl.location_id, sl.name;
```

### Query 3: Check for Unassigned Locations

```sql
SELECT 
    svl.id,
    sp.name as product,
    svl.quantity,
    svl.value
FROM stock_valuation_layer svl
LEFT JOIN product_product sp ON svl.product_id = sp.id
WHERE svl.location_id IS NULL
LIMIT 10;
```

### Query 4: Verify COGS Accuracy

```sql
SELECT 
    aml.id,
    aml.date,
    aa.name as account,
    aml.debit,
    aml.credit,
    aml.name as description
FROM account_move_line aml
LEFT JOIN account_account aa ON aml.account_id = aa.id
WHERE aa.name LIKE '%COGS%'
  AND aml.date >= '2025-01-01'
ORDER BY aml.date DESC
LIMIT 20;
```

## Troubleshooting

### Problem: location_id field not visible in Valuation Layer

**Solution:**
1. Refresh browser (Ctrl+R or Cmd+R)
2. Clear browser cache
3. Verify module is installed (Installed apps list)
4. Restart Odoo service

### Problem: COGS amount seems incorrect

**Check:**
1. Verify FIFO queue: `service.get_valuation_layer_queue(product, location)`
2. Check unit_cost values on layers
3. Confirm shortage policy setting
4. Review quantity consumed from each layer

### Problem: Layers created without location_id

**Solution:**
1. Run migration script: `python -m odoo.bin shell ...`
2. Execute: `from odoo.addons.stock_fifo_by_location.migrations import populate_location_id; populate_location_id.populate_location_id(env)`
3. Check for unassigned locations query (see above)

### Problem: Error during delivery validation

**Check:**
1. Is shortage policy set to 'error'?
2. Is there sufficient stock at delivery location?
3. Enable debug_mode and check logs
4. Verify location_id values on stock moves

## Performance Testing

For large datasets, monitor:

1. **Query Time:** Valuation layer lookups should be <100ms
2. **Memory:** Large FIFO queues should stay within reasonable limits
3. **Storage:** Index on location_id reduces storage overhead

Monitor via:
```sql
-- Check index usage
SELECT * FROM pg_stat_user_indexes 
WHERE relname = 'stock_valuation_layer';

-- Analyze query performance
EXPLAIN ANALYZE
SELECT * FROM stock_valuation_layer 
WHERE product_id = 123 AND location_id = 456 
ORDER BY create_date ASC;
```

## Sign-Off

Once all scenarios pass:

- [ ] Scenario 1: Basic receiving ✅
- [ ] Scenario 2: Location isolation ✅
- [ ] Scenario 3: FIFO calculation ✅
- [ ] Scenario 4: Shortage error ✅
- [ ] Scenario 5: Shortage fallback ✅
- [ ] Scenario 6: Internal transfer ✅
- [ ] Scenario 7: Multiple locations ✅
- [ ] Python tests passed ✅
- [ ] Database queries verified ✅

Module is ready for production deployment.
