# Transit Location Migration - Quick Reference

## 🚀 Quick Start

### 1. Analyze Transit Locations
```python
# In Odoo shell: odoo-bin shell -d your_database
from odoo.addons.stock_fifo_by_location.migrations import populate_location_id

stats = populate_location_id.analyze_transit_locations(env)
```

### 2. Migrate Transit Layers
```python
result = populate_location_id.populate_transit_location_layers(env)
print(f"Migrated: {result['successful']}")
```

### 3. Migrate All Remaining
```python
result = populate_location_id.populate_location_id(env)
print(f"Total: {result['successful']}, Failed: {result['failed']}")
```

### 4. Verify
```python
# Check remaining unmigrated
remaining = env['stock.valuation.layer'].search_count([('location_id', '=', False)])
print(f"Remaining: {remaining}")
```

## 📊 Migration Functions

| Function | Purpose | Use When |
|----------|---------|----------|
| `analyze_transit_locations(env)` | Report transit usage | Before migration |
| `populate_transit_location_layers(env)` | Migrate transit only | Have transit moves |
| `populate_location_id(env)` | Migrate all layers | Main migration |
| `populate_location_id_by_context(env)` | Fast migration | Clean data |

## 🔄 Transit Scenarios Handled

### Scenario 1: Inter-Warehouse Transfer
```
WH-A → Transit → WH-B
```
**Layers created:**
- WH-A: Negative (goods leaving)
- Transit: Positive (in transit), then Negative (leaving transit)
- WH-B: Positive (goods arriving)

### Scenario 2: Direct Transit Delivery
```
Supplier → Transit → Warehouse
```
**Layers created:**
- Transit: Positive (received from supplier)
- Transit: Negative (leaving transit)
- Warehouse: Positive (received)

### Scenario 3: Transit Shipment
```
Warehouse → Transit → Customer
```
**Layers created:**
- Warehouse: Negative (shipped)
- Transit: Positive (in transit)
- Transit: Negative (delivered)

## 🧪 Testing

### Run All Tests
```bash
# In Odoo shell
exec(open('/opt/instance1/odoo17/custom-addons/test_transit_migration.py').read())
```

### Individual Tests
```python
from test_transit_migration import *

test_analyze_transit_locations(env)
test_populate_transit_layers(env)
test_verify_transit_consistency(env)
```

## ✅ Verification Checklist

- [ ] Backup database before migration
- [ ] Run `analyze_transit_locations()` for statistics
- [ ] Run `populate_transit_location_layers()` for transit
- [ ] Run `populate_location_id()` for remaining layers
- [ ] Verify no layers missing location: `search_count([('location_id', '=', False)])`
- [ ] Check failed layers manually if any
- [ ] Run consistency verification test
- [ ] Test a sample inter-warehouse transfer

## 🔍 Troubleshooting

### No Transit Locations Found
```python
# Check if transit locations exist
transit_locs = env['stock.location'].search([('usage', '=', 'transit')])
print(f"Transit locations: {len(transit_locs)}")
```

### Many Failed Layers
```python
# Review failed layers
failed_layers = env['stock.valuation.layer'].browse(result['failed_ids'])
for layer in failed_layers[:10]:
    print(f"Layer {layer.id}: {layer.product_id.name}, Move: {layer.stock_move_id.id if layer.stock_move_id else 'None'}")
```

### Inconsistent Transit Layers
```python
# Fix inconsistent layers
from test_transit_migration import test_verify_transit_consistency
result = test_verify_transit_consistency(env)
```

## 📝 Common SQL Queries

### Check Migration Progress
```sql
-- Total layers without location
SELECT COUNT(*) FROM stock_valuation_layer WHERE location_id IS NULL;

-- Transit layers
SELECT COUNT(*) FROM stock_valuation_layer svl
JOIN stock_location sl ON svl.location_id = sl.id
WHERE sl.usage = 'transit';

-- Layers by location type
SELECT sl.usage, COUNT(*) as count
FROM stock_valuation_layer svl
LEFT JOIN stock_location sl ON svl.location_id = sl.id
GROUP BY sl.usage;
```

### Find Transit Moves
```sql
-- Moves involving transit
SELECT 
    sm.id as move_id,
    sm.name,
    sl_from.name as from_location,
    sl_from.usage as from_usage,
    sl_to.name as to_location,
    sl_to.usage as to_usage
FROM stock_move sm
JOIN stock_location sl_from ON sm.location_id = sl_from.id
JOIN stock_location sl_to ON sm.location_dest_id = sl_to.id
WHERE (sl_from.usage = 'transit' OR sl_to.usage = 'transit')
  AND sm.state = 'done'
LIMIT 10;
```

## 🎯 Best Practices

1. **Always backup** before running migration
2. **Test in staging** environment first
3. **Run analysis** before migration to understand scope
4. **Migrate in order**: Transit first, then all remaining
5. **Verify results** after each step
6. **Review failed layers** manually
7. **Document** any custom fixes needed

## 📚 Related Documentation

- Full guide: `TRANSIT_LOCATION_MIGRATION_GUIDE.md`
- Module README: `README.md`
- Transit analysis: `TRANSIT_LOCATION_VALUATION_ANALYSIS.md`
- Test script: `/opt/instance1/odoo17/custom-addons/test_transit_migration.py`

## ⚡ One-Liner Complete Migration

```python
# Complete migration in one go (use with caution)
from odoo.addons.stock_fifo_by_location.migrations import populate_location_id as m
a = m.analyze_transit_locations(env)
t = m.populate_transit_location_layers(env)
r = m.populate_location_id(env)
print(f"Transit: {a['transit_locations']}, Migrated: {t['successful']+r['successful']}, Failed: {r['failed']}")
```

## 🔗 Quick Links

- Module path: `/opt/instance1/odoo17/custom-addons/stock_fifo_by_location`
- Migration script: `migrations/populate_location_id.py`
- Test script: `/opt/instance1/odoo17/custom-addons/test_transit_migration.py`
