# Stock By Location - Quick Reference

## Installation
```bash
cd /opt/instance1/odoo17/custom-addons/stock_by_locations
./install_stock_by_locations.sh your_database
```

## Essential Configuration

### 1. Main Warehouse (Required)
**Menu:** Inventory > Configuration > Warehouses  
**Action:** Open warehouse → Enable "Main Warehouse?"  
**Purpose:** Sets which warehouse determines product.standard_price

### 2. Product Category (Required)
**Menu:** Inventory > Configuration > Product Categories  
**Action:** Set "Costing Method" = "AVCO by Location"  
**Purpose:** Enables per-location cost tracking

### 3. Locations (Optional)
**Menu:** Inventory > Configuration > Locations  
**Settings:**
- ☐ **Exclude from Product Cost** - Exclude this location from cost calculations
- ☐ **Apply in Sale Order** - Make available in "Deliver From" dropdown

## Usage Patterns

### View Product Costs by Location
**Menu:** Inventory > Products > [Product] > Product Cost tab  
**Shows:** Current quantity and cost for each location

### View Cost History
**Menu:** Base > Product Cost History  
**Shows:** Complete audit trail of all cost changes

### Create Sale Order from Specific Location
1. Sales > Orders > Create
2. Select **"Deliver From"** location (required)
3. System auto-selects picking type
4. View cost on order lines

### Internal Transfer
**Result:** 
- OUT valuation from source (negative qty, source cost)
- IN valuation to destination (positive qty)
- Destination cost updated with new average
- Cost history record created

## Key Fields

### Product (product.product)
- `main_wh_cost` - Cost in main warehouse (replaces standard_price in views)
- `product_cost_ids` - Current cost per location (computed)
- `product_cost_history_ids` - All historical cost changes

### Stock Warehouse (stock.warehouse)
- `is_main_warehouse` - Boolean flag

### Stock Location (stock.location)
- `exclude_from_product_cost` - Boolean
- `apply_in_sale` - Boolean

### Sale Order (sale.order)
- `picking_location_id` - Selected delivery location (required)
- `picking_type_id` - Auto-populated picking type

### Sale Order Line (sale.order.line)
- `purchase_price` - Location-specific cost

### Stock Valuation Layer (stock.valuation.layer)
- `location_id` - Which location this valuation applies to

## Costing Logic

### Receipt to Main Warehouse
```
1. Product received → Qty: 100, Cost: 10.00
2. Stock Valuation Layer created (location_id = main_wh)
3. Cost History created (old avg, new avg)
4. Product.standard_price updated to 10.00
```

### Receipt to Other Location
```
1. Product received → Qty: 50, Cost: 12.00
2. Stock Valuation Layer created (location_id = other_loc)
3. Cost History created for that location
4. Product.standard_price UNCHANGED (not main warehouse)
5. Location has independent cost of 12.00
```

### Internal Transfer
```
Source Location (WH1): 100 @ 10.00
Transfer: 50 units to WH2 (currently 20 @ 15.00)

Result:
- WH1: 50 @ 10.00 (OUT valuation: -50 @ 10.00)
- WH2: 70 @ 13.57 (IN valuation: +50 @ 10.00, avg: (20*15 + 50*10)/70)
- Cost history created for WH2
- If WH2 is main warehouse, standard_price → 13.57
```

### Delivery to Customer
```
Deliver from WH2: 10 units
- OUT valuation: -10 @ WH2_cost
- WH2 quantity reduced
- Cost remains same (AVCO)
```

## Menu Locations

### Configuration
```
Inventory > Configuration > Warehouses        → Set main warehouse
Inventory > Configuration > Product Categories → Set AVCO by Location
Inventory > Configuration > Locations         → Configure locations
```

### Operations
```
Sales > Orders                    → Create order with location
Inventory > Products              → View product costs
Base > Product Cost History       → View cost history
Inventory > Operations > Transfers → Internal transfers
```

### Reports
```
Inventory > Reporting > Valuation  → Stock valuation (with location)
```

## Common Issues

### ❌ Sale Order: "No Inventory Operation found with location!"
**Solution:** Configure picking type with selected location as source

### ❌ Product cost not updating
**Solution:** 
- Check product category costing method = 'avco_by_location'
- Verify location is main warehouse for standard_price update
- Check cost history for actual updates

### ❌ Location not in "Deliver From" dropdown
**Solution:** Location settings → Enable "Apply in Sale Order"

### ❌ Cannot update standard_price directly
**Solution:** By design - use stock moves or revaluation for AVCO products

## API Examples

### Get Product Cost in Location
```python
product = env['product.product'].browse(1)
location = env['stock.location'].browse(8)
cost = product.get_last_cost_history(location=location)
```

### Get All Location Costs
```python
product = env['product.product'].browse(1)
for cost in product.product_cost_ids:
    print(f"{cost.location_id.name}: {cost.qty} @ {cost.standard_price}")
```

### Create Cost History
```python
env['product.cost.location.history'].create({
    'product_id': product.id,
    'location_id': location.id,
    'standard_price': 15.50,
    'qty': 100,
    'date': fields.Datetime.now(),
    'company_id': env.company.id,
    'currency_id': env.company.currency_id.id,
})
```

### Check if Internal Move
```python
move = env['stock.move'].browse(123)
if move._is_internal():
    print("Internal transfer between valued locations")
```

## Troubleshooting Commands

### Check Module Status
```bash
# Shell
/opt/instance1/odoo17/odoo-bin shell -d your_db
>>> env['ir.module.module'].search([('name','=','stock_by_locations')]).state
```

### View Logs
```bash
tail -f /var/log/odoo/odoo17.log | grep -i "stock_by_locations\|valuation\|cost"
```

### Test Cost Calculation
```python
product = env['product.product'].search([('cost_method','=','avco_by_location')], limit=1)
product._compute_product_cost()
print(f"Costs: {[(c.location_id.name, c.standard_price) for c in product.product_cost_ids]}")
```

### Verify Main Warehouse
```python
wh = env['stock.warehouse'].search([('is_main_warehouse','=',True)])
print(f"Main: {wh.name if wh else 'NONE SET'}")
```

## Performance Tips

### For Many Locations
```python
# Instead of computing all locations
product._compute_product_cost()

# Compute specific location only
location = env['stock.location'].browse(8)
product.with_context(quant_location=location)._compute_product_cost()
```

### For Date-Specific Costs
```python
# Get cost at specific date
cost = product.get_last_cost_history(
    location=location,
    to_date='2024-01-01'
)
```

### Batch Operations
```python
# Use batch creation
history_vals = []
for move in moves:
    history_vals.append({...})
env['product.cost.location.history'].create(history_vals)
```

## Support Files
- `README.md` - Complete documentation
- `UPGRADE_TO_ODOO17.md` - Upgrade guide
- `ODOO17_IMPLEMENTATION_SUMMARY.md` - Technical summary
- `install_stock_by_locations.sh` - Installation script

## Version Info
- **Module Version:** 17.0.0.0.0
- **Odoo Version:** 17.0
- **License:** OPL-1
- **Author:** Techultra Solutions Private Limited
