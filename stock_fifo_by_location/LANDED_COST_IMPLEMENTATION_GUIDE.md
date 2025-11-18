# Stock FIFO by Location - Landed Cost Implementation Guide

## 🎯 Quick Start

### Installation

1. **Update module dependencies:**
   ```
   Module now requires: stock, stock_account, stock_landed_costs
   ```

2. **Reinstall module:**
   ```bash
   # Restart Odoo to apply changes
   sudo systemctl restart instance1
   
   # Or via UI: Apps → Update Apps List → Stock FIFO by Location → Upgrade
   ```

3. **Verify installation:**
   ```bash
   # Check models are created
   python -m odoo.bin shell -d your_database
   >>> env['stock.valuation.layer.landed.cost']
   >>> env['stock.landed.cost.allocation']
   >>> env['stock.landed.cost']._fields['location_landed_cost_ids']
   ```

## 📊 Typical Workflow

### Scenario: Multi-warehouse with Landed Costs

#### Step 1: Receive Goods at Main Warehouse

```
1. Create Purchase Order for Product X
   - Qty: 100 units
   - Cost: $100/unit = $10,000

2. Create Receipt
   - Destination: Main Warehouse → Location A
   - Stock Move validates
   - stock.valuation.layer created:
     · location_id = Location A
     · quantity = 100
     · unit_cost = $100
     · value = $10,000

3. Receive Landed Cost Invoice
   - Freight: $500
   - Insurance: $300
   - Total LC: $800

4. Create Landed Cost
   - Type: Receipt
   - Picking: PO Receipt
   - Cost Lines: Freight $500 + Insurance $300
   - Additional Cost to Account: $800

5. Post Landed Cost
   - System validates
   - stock.valuation.layer.landed.cost created:
     · valuation_layer_id = layer from step 2
     · location_id = Location A
     · landed_cost_value = $800
     · unit_landed_cost = $8/unit
   - Result: Location A inventory now @ $108/unit effective cost
```

#### Step 2: Transfer to Secondary Warehouse

```
6. Create Internal Transfer
   - From: Location A (Main Warehouse)
   - To: Location B (Secondary Warehouse)
   - Qty: 50 units
   - State: draft

7. Validate Transfer
   - Stock move processes
   - System automatically:
     a) Detects this is an internal transfer
     b) Identifies it involves landed cost
     c) Calculates proportion: 50 transferred / 100 available = 50%
     d) LC to transfer: $800 × 50% = $400
     e) Updates landed cost allocations:
        - Location A: $800 → $400 (50 units remaining)
        - Location B: $0 → $400 (50 units received)
     f) Creates allocation history record
   
   - Result:
     · Location A: 50 units @ $108/unit ($400 LC)
     · Location B: 50 units @ $108/unit ($400 LC)
```

#### Step 3: Transfer to Tertiary Warehouse

```
8. Transfer from Location B to Location C
   - Qty: 25 units (50% of Location B inventory)
   
9. System calculates:
   - Proportion: 25/50 = 50% of Location B's LC
   - LC transfer: $400 × 50% = $200
   
   - Result:
     · Location A: 50 units, $400 LC ✓
     · Location B: 25 units, $200 LC ✓
     · Location C: 25 units, $200 LC ✓
     · Total LC preserved: $400 + $200 + $200 = $800 ✓
```

#### Step 4: Deliver from Specific Location

```
10. Create Sales Order
    - Product X: 30 units
    - Deliver from: Location C (Tertiary Warehouse)

11. Create Delivery
    - Location source: Location C
    - Pick 30 units

12. Post Delivery
    - FIFO consumption from Location C:
      · Consumes 25 units @ $108/unit = $2,700
      · Still need 5 more units
      · (Or ERROR if shortage_policy = 'error')
    
    - Journal Entry:
      Debit: Cost of Goods Sold    $2,700
        Credit: Inventory             $2,700
      
      (Location C's FIFO cost applies, not Location A's)
```

## 🛠️ Implementation Checklist

### Phase 1: Installation
- [ ] Backup database
- [ ] Verify `stock_landed_costs` module is installed
- [ ] Update module version in `__manifest__.py`
- [ ] Reinstall `stock_fifo_by_location` module
- [ ] Verify 2 new models created:
  - [ ] `stock.valuation.layer.landed.cost`
  - [ ] `stock.landed.cost.allocation`

### Phase 2: Migration (If Existing Data)
- [ ] Identify existing landed costs
- [ ] Verify location_id populated on valuation layers
- [ ] Run landed cost allocation for historical moves:

```python
# Via shell, for each historical landed cost:
landed_cost = env['stock.landed.cost'].browse(lc_id)
if landed_cost.state == 'done':
    landed_cost._allocate_landed_costs_by_location()
```

### Phase 3: Testing
- [ ] Test incoming receipt with landed cost
- [ ] Test internal transfer with landed cost
- [ ] Verify allocation history created
- [ ] Verify COGS calculation includes landed cost
- [ ] Test multiple cascading transfers
- [ ] Verify journal entries are correct

### Phase 4: Deployment
- [ ] Document company-specific configurations
- [ ] Train users on new functionality
- [ ] Monitor logs for issues
- [ ] Verify accounting reconciliation

## 📋 Configuration & Settings

### Default Configuration

No additional configuration needed. The module uses:
- Existing `stock_fifo_by_location` settings
- Standard Odoo landed cost configuration
- Company accounting settings

### Optional: Extend Behavior

**Example: Log all landed cost allocations**

```python
# In custom module inheriting stock_fifo_by_location
_logger = logging.getLogger(__name__)

class CustomStockMove(models.Model):
    _inherit = 'stock.move'
    
    def _allocate_landed_cost_on_transfer(self, move, layers):
        _logger.info(f"Allocating LC for move {move.name}")
        result = super()._allocate_landed_cost_on_transfer(move, layers)
        _logger.info(f"LC allocation complete")
        return result
```

## 🔍 Monitoring & Verification

### Daily Operations Checklist

**After receiving goods with landed cost:**
```python
# Verify landed cost is recorded
product = env['product.product'].browse(product_id)
location = env['stock.location'].browse(location_id)

lc_total = env['stock.valuation.layer'].get_landed_cost_at_location(
    product, location
)
print(f"Landed cost at {location.name}: {lc_total}")
```

**Before transferring inventory:**
```python
# Verify source location has correct landed cost
source_lc = env['stock.valuation.layer'].get_landed_cost_at_location(
    product, source_location
)
print(f"Source LC: {source_lc}")

# Calculate what will be transferred
qty_to_transfer = 50
proportion = qty_to_transfer / available_qty
lc_to_transfer = source_lc * proportion
print(f"LC to transfer: {lc_to_transfer}")
```

**After delivery:**
```python
# Verify COGS includes landed cost
cost_info = env['fifo.service'].calculate_fifo_cost_with_landed_cost(
    product, location, qty=30
)
print(f"Total COGS: {cost_info['cost']}")
print(f"Including LC: {cost_info['landed_cost']}")
```

## 🐛 Troubleshooting Guide

### Problem 1: Landed Cost Not Allocated During Transfer

**Symptoms:**
- Internal transfer created
- Allocation history not created
- Landed cost not showing at destination

**Diagnosis:**
```sql
-- Check if moved_id is in history
SELECT * FROM stock_landed_cost_allocation 
WHERE move_id = <transfer_move_id>;

-- Check valuation layers
SELECT * FROM stock_valuation_layer 
WHERE stock_move_id = <transfer_move_id>;

-- Check landed cost records at source
SELECT * FROM stock_valuation_layer_landed_cost 
WHERE location_id = <source_location_id>;
```

**Solutions:**
1. Verify transfer is marked as 'done':
   ```python
   move = env['stock.move'].browse(move_id)
   print(move.state)  # Should be 'done'
   ```

2. Manually trigger allocation:
   ```python
   move = env['stock.move'].browse(move_id)
   layers = env['stock.valuation.layer'].search([
       ('stock_move_id', '=', move.id)
   ])
   move._allocate_landed_cost_on_transfer(move, layers)
   ```

3. Check for errors in logs:
   ```bash
   tail -f /var/log/odoo/odoo.log | grep "landed_cost"
   ```

### Problem 2: Landed Cost Value Discrepancy

**Symptoms:**
- Sum of LC at locations ≠ total LC applied
- Missing or extra LC allocated

**Diagnosis:**
```python
product = env['product.product'].browse(product_id)

# Get all locations with inventory
svl_records = env['stock.valuation.layer'].search([
    ('product_id', '=', product_id),
    ('quantity', '>', 0),
])

locations = svl_records.mapped('location_id')
total_lc = 0

for location in locations:
    lc = env['stock.valuation.layer'].get_landed_cost_at_location(
        product, location
    )
    print(f"{location.name}: {lc}")
    total_lc += lc

print(f"Total LC: {total_lc}")
print(f"Expected: <total_original_lc>")
```

**Solutions:**
1. Check allocation history for any failed allocations
2. Look for partial transfers
3. Verify no rounding errors in calculations
4. Run landed cost recomputation if needed

### Problem 3: COGS Calculation Incorrect

**Symptoms:**
- COGS doesn't include landed cost
- Cost appears too low

**Diagnosis:**
```python
# Compare regular FIFO cost vs with LC
cost_without_lc = env['fifo.service'].calculate_fifo_cost(
    product, location, qty=10
)

cost_with_lc = env['fifo.service'].calculate_fifo_cost_with_landed_cost(
    product, location, qty=10
)

print(f"FIFO: {cost_without_lc['cost']}")
print(f"FIFO + LC: {cost_with_lc['cost']}")
print(f"Difference: {cost_with_lc['cost'] - cost_without_lc['cost']}")
```

**Solutions:**
1. Verify landed cost records exist:
   ```sql
   SELECT * FROM stock_valuation_layer_landed_cost 
   WHERE location_id = <location_id>;
   ```

2. Check if calling correct method:
   - Use `calculate_fifo_cost_with_landed_cost()` NOT `calculate_fifo_cost()`

3. Verify landed cost was validated (state = 'done')

## 📈 Performance Considerations

### Optimization for Large Datasets

**1. Indexing:**
The following fields are indexed for fast queries:
- `stock.valuation.layer.landed.cost.location_id`
- `stock.valuation.layer.landed.cost.valuation_layer_id`

**2. Query Optimization:**
When calculating costs for many products:
```python
# GOOD: Use service method (optimized)
for product in products:
    lc = env['fifo.service'].get_landed_cost_at_location(product, location)

# AVOID: Direct queries in loop
for product in products:
    for layer in env['stock.valuation.layer'].search([...]):
        ...  # Slow - many queries
```

**3. Caching:**
For frequently accessed values, cache in context:
```python
context = {'landed_cost_cache': {}}
# Then reuse in operations
```

## 🔐 Security & Audit Trail

### Access Control

Add groups in `security/ir.model.access.csv`:

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_valuation_layer_lc_user,Valuation Layer LC User,model_stock_valuation_layer_landed_cost,stock.group_stock_user,1,0,0,0
access_allocation_user,Landed Cost Allocation User,model_stock_landed_cost_allocation,stock.group_stock_user,1,0,0,0
```

### Audit Trail

All allocations are recorded in `stock.landed.cost.allocation`:
- Every transfer creates a history record
- Records include before/after values
- Can be queried for audit purposes

```python
# Generate audit report
allocations = env['stock.landed.cost.allocation'].search([
    ('create_date', '>=', date_from),
    ('create_date', '<=', date_to),
])

for alloc in allocations:
    print(f"{alloc.move_id.name}: {alloc.landed_cost_transferred} transferred")
```

## 🎓 User Guide

### For Warehouse Managers

**Receiving with Landed Costs:**
1. Create Purchase Order as normal
2. Receive goods (creates valuation layer)
3. Post landed cost invoice
4. Create Landed Cost document
5. Post Landed Cost
6. System automatically tracks at each location

**Transferring Between Warehouses:**
1. Create internal transfer as normal
2. Validate transfer
3. System automatically:
   - Calculates landed cost proportion
   - Allocates to destination location
   - Creates audit trail
4. Transfer is complete with proper landed cost tracking

**Delivering to Customers:**
1. Create Sales Order with "Deliver From" location
2. Deliver goods
3. COGS automatically calculated using Location-specific FIFO cost (including LC)

### For Accountants

**Monthly Reconciliation:**
```sql
-- Verify inventory value = sum of SVL values
SELECT 
    product_id,
    SUM(value + (
        SELECT COALESCE(SUM(landed_cost_value), 0)
        FROM stock_valuation_layer_landed_cost svlc
        WHERE svlc.valuation_layer_id = svl.id
    )) as total_value
FROM stock_valuation_layer svl
WHERE company_id = <company_id>
GROUP BY product_id;
```

**Landed Cost Tracking:**
```sql
-- Verify all LC allocated and accounted for
SELECT 
    slc.name,
    SUM(lc.landed_cost_value) as total_lc_allocated
FROM stock_landed_cost slc
LEFT JOIN stock_valuation_layer_landed_cost lc 
    ON lc.landed_cost_id = slc.id
WHERE slc.state = 'done'
  AND slc.company_id = <company_id>
GROUP BY slc.name;
```

## 📞 Support & Documentation

For additional information, see:
- `LANDED_COST_SUPPORT.md` - Technical details
- `README.md` - Module overview
- `ANALYSIS_STOCK_FIFO_BY_LOCATION.md` - Architecture analysis
- Test cases in `tests/test_fifo_by_location.py`

---

**Version:** 17.0.1.0.0 with Landed Cost Support  
**Last Updated:** 2568-11-17  
**Module:** stock_fifo_by_location
