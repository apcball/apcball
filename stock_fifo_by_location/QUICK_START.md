# Quick Start Guide - Stock FIFO by Location

## 60-Second Installation

### 1. Copy Module (30 seconds)
```bash
cd /opt/instance1/odoo17/custom-addons
ls -la stock_fifo_by_location/
# Should show module folder with all files
```

### 2. Restart Odoo (20 seconds)
```bash
sudo systemctl restart instance1
# Wait for service to restart
```

### 3. Install in Odoo (10 seconds)
1. Login to Odoo
2. **Apps** → **Update Apps List** (Ctrl+R)
3. Search: `stock_fifo_by_location`
4. Click **Install**

✅ **Module installed!**

---

## First Test (5 minutes)

### Create a Receipt to Location A

1. **Purchases** → **Create PO**
   - Product: Any product with FIFO costing
   - Qty: 10
   - Price: $100

2. **Confirm** → **Receive**
   - Set destination to **Location A**

3. **Verify in Odoo**
   - Go to: **Inventory** → **Valuation Layers**
   - Find your receipt
   - Check: `location_id` = "Location A" ✅

### Check FIFO Queue

```python
# In Odoo Shell (python -m odoo.bin shell -d your_database):
product = env['product.product'].search([('name', 'like', 'Your Product')], limit=1)
location_a = env['stock.location'].search([('name', '=', 'Location A')], limit=1)

queue = env['fifo.service'].get_valuation_layer_queue(product, location_a)
for layer in queue:
    print(f"Layer {layer.id}: {layer.quantity} units @ ${layer.unit_cost}")
```

---

## Configuration (2 minutes)

### Set Shortage Policy

**Settings** → **Technical** → **Parameters**

Search: `stock_fifo_by_location.shortage_policy`

- **error** (default): Block deliveries if insufficient stock at location
- **fallback**: Allow pulling from alternative locations

---

## Migration (For Existing Data)

If you have prior stock movements:

```bash
python -m odoo.bin shell -d your_database

# In shell:
from odoo.addons.stock_fifo_by_location.migrations import populate_location_id
result = populate_location_id.populate_location_id(env)

# Review output for any items needing manual attention
exit()
```

---

## Run Tests (2 minutes)

### Via Pytest
```bash
cd /path/to/odoo17
pytest -xvs addons/stock_fifo_by_location/tests/
```

### Via Odoo UI
1. **Apps** → **Stock FIFO by Location**
2. Look for **Tests** button
3. Click to run test suite

---

## Common Tasks

### Query 1: Check Available Stock at Location

```python
env['fifo.service'].get_available_qty_at_location(product, location)
```

### Query 2: Calculate COGS for Sale

```python
cost_info = env['fifo.service'].calculate_fifo_cost(
    product, 
    location, 
    quantity=12
)
print(f"COGS: ${cost_info['cost']}")
print(f"Unit cost: ${cost_info['unit_cost']}")
```

### Query 3: Validate Stock Before Delivery

```python
result = env['fifo.service'].validate_location_availability(
    product, 
    location, 
    quantity=12,
    allow_fallback=False
)
print(f"Available: {result['available']}")
print(f"Shortage: {result['shortage']}")
```

---

## Troubleshooting

### Problem: location_id field not showing

**Solution:** Refresh browser (Ctrl+R), clear cache, restart Odoo

### Problem: Tests failing

**Solution:** 
1. Check Odoo logs: `/var/log/odoo/instance1.log`
2. Verify stock and stock_account modules installed
3. Run: `python -m odoo.bin -d your_database -m stock_fifo_by_location --test-enable`

### Problem: Migration not working

**Solution:**
1. Check database connection
2. Run: `psql -U odoo -d your_database -c "SELECT COUNT(*) FROM stock_valuation_layer;"`
3. Check for unassigned: `SELECT COUNT(*) FROM stock_valuation_layer WHERE location_id IS NULL;`

---

## Key Files

| File | Purpose |
|------|---------|
| `README.md` | Full documentation (50+ pages) |
| `MANUAL_TESTING.md` | Test scenarios with steps |
| `INSTALLATION_CHECKLIST.md` | Complete deployment guide |
| `DELIVERY_SUMMARY.md` | What's included & acceptance criteria |
| `models/fifo_service.py` | Service methods for FIFO logic |
| `tests/test_fifo_by_location.py` | Unit tests (10+ scenarios) |

---

## Full Documentation

For complete information, see:

1. **Feature Overview** → `README.md` (Architecture section)
2. **How to Use** → `README.md` (Usage section)
3. **Configuration** → `README.md` (Configuration section)
4. **Manual Testing** → `MANUAL_TESTING.md`
5. **Deployment** → `INSTALLATION_CHECKLIST.md`
6. **Code Examples** → `tests/test_fifo_by_location.py`

---

## Support

**For questions:**
1. Check `README.md` → Troubleshooting section
2. Review `MANUAL_TESTING.md` for examples
3. Check Odoo logs for errors
4. Contact development team with specific error

**Module Status:** ✅ Production Ready

---

**You're all set!** Start using per-location FIFO cost accounting now. 🎉
