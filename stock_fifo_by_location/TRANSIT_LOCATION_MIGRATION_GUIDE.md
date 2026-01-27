# Transit Location Migration Guide

## Overview

This guide explains how to migrate existing stock valuation layers to support Transit locations in the `stock_fifo_by_location` module.

Transit locations are used in Odoo for inter-warehouse transfers, representing goods in transit between warehouses. This module now fully supports FIFO cost accounting for transit locations.

## Transit Location Scenarios

### Scenario 1: Inter-Warehouse Transfer
```
Warehouse A → Transit Location → Warehouse B
```

**Step 1: Warehouse A → Transit**
- Negative valuation layer at Warehouse A (goods leaving)
- Positive valuation layer at Transit Location (goods in transit)

**Step 2: Transit → Warehouse B**
- Negative valuation layer at Transit Location (goods leaving transit)
- Positive valuation layer at Warehouse B (goods arriving)

### Scenario 2: Direct Supplier to Transit
```
Supplier → Transit Location → Warehouse
```

**Purchase Order Delivery:**
- Positive valuation layer at Transit Location (goods received from supplier)
- Then Transit → Warehouse creates layers as in Scenario 1, Step 2

### Scenario 3: Transit to Customer
```
Warehouse → Transit Location → Customer
```

**Sales Order Delivery:**
- Warehouse → Transit creates layers as in Scenario 1, Step 1
- Negative valuation layer at Transit Location (goods delivered to customer)

## Migration Functions

### 1. `populate_location_id(env)`

**Main migration function** - Processes all valuation layers without location_id.

```python
from odoo.addons.stock_fifo_by_location.migrations import populate_location_id

# Run main migration
result = populate_location_id.populate_location_id(env)

# Check results
print(f"Total: {result['total']}")
print(f"Successful: {result['successful']}")
print(f"Failed: {result['failed']}")
```

**Features:**
- Handles all location types (internal, transit, supplier, customer, production)
- Intelligent location detection based on move type and layer quantity
- Detailed logging with reason for each assignment
- Returns failed layer IDs for manual review

### 2. `populate_transit_location_layers(env)`

**Transit-specific migration** - Focuses only on transit location scenarios.

```python
from odoo.addons.stock_fifo_by_location.migrations import populate_location_id

# Run transit-only migration
result = populate_location_id.populate_transit_location_layers(env)

# Check transit statistics
print(f"Internal → Transit: {result['stats']['internal_to_transit']}")
print(f"Transit → Internal: {result['stats']['transit_to_internal']}")
print(f"Transit → Transit: {result['stats']['transit_to_transit']}")
```

**Use Cases:**
- When you only need to fix transit-related layers
- Faster than full migration if you have many layers
- Provides detailed breakdown by transfer type

### 3. `analyze_transit_locations(env)`

**Analysis function** - Reports on transit location usage without making changes.

```python
from odoo.addons.stock_fifo_by_location.migrations import populate_location_id

# Analyze transit locations
stats = populate_location_id.analyze_transit_locations(env)

# Review statistics
print(f"Transit locations: {stats['transit_locations']}")
print(f"Transit moves: {stats['transit_moves']}")
print(f"Layers missing location: {stats['transit_missing']}")
```

**Provides:**
- List of all transit locations in the system
- Count of moves involving each transit location
- Count of valuation layers with/without location_id
- Overall statistics for planning migration

### 4. `populate_location_id_by_context(env, only_missing=True)`

**Fast migration** - Simplified logic for quick migration.

```python
from odoo.addons.stock_fifo_by_location.migrations import populate_location_id

# Run context-based migration
result = populate_location_id.populate_location_id_by_context(env)

print(f"Migrated: {result['migrated']}")
print(f"Skipped: {result['skipped']}")
```

**Characteristics:**
- Faster than main migration
- Less detailed logging
- Good for clean datasets without edge cases

## Step-by-Step Migration Process

### Step 1: Backup Database
```bash
# Create backup before migration
pg_dump -U odoo -d your_database > backup_before_migration.sql
```

### Step 2: Analyze Current State
```python
# In Odoo shell
odoo-bin shell -d your_database

>>> from odoo.addons.stock_fifo_by_location.migrations import populate_location_id

# Check how many layers need migration
>>> env['stock.valuation.layer'].search_count([('location_id', '=', False)])

# Analyze transit locations
>>> stats = populate_location_id.analyze_transit_locations(env)
```

### Step 3: Run Transit Migration
```python
# Migrate transit-related layers first
>>> result = populate_location_id.populate_transit_location_layers(env)

# Review results
>>> print(f"Transit layers migrated: {result['successful']}")
>>> if result['failed'] > 0:
...     print(f"Failed IDs: {result['failed_ids']}")
```

### Step 4: Run Full Migration
```python
# Migrate remaining layers
>>> result = populate_location_id.populate_location_id(env)

# Review results
>>> print(f"Total migrated: {result['successful']}")
>>> print(f"Failed: {result['failed']}")
```

### Step 5: Verify Results
```python
# Check if any layers still missing location
>>> remaining = env['stock.valuation.layer'].search_count([('location_id', '=', False)])
>>> print(f"Layers still without location: {remaining}")

# Verify transit location consistency
>>> transit_layers = env['stock.valuation.layer'].search([
...     ('location_id.usage', '=', 'transit')
... ])
>>> print(f"Transit layers: {len(transit_layers)}")
```

### Step 6: Manual Review of Failed Layers
```python
# Review failed layers
>>> if result['failed_ids']:
...     failed_layers = env['stock.valuation.layer'].browse(result['failed_ids'])
...     for layer in failed_layers:
...         print(f"Layer {layer.id}: Product {layer.product_id.name}, Move {layer.stock_move_id.id if layer.stock_move_id else 'None'}")
```

## Using the Test Script

A comprehensive test script is available at `/opt/instance1/odoo17/custom-addons/test_transit_migration.py`.

### Run All Tests
```bash
# In Odoo shell
odoo-bin shell -d your_database
>>> exec(open('/opt/instance1/odoo17/custom-addons/test_transit_migration.py').read())
```

### Run Individual Tests
```python
# In Odoo shell
>>> from test_transit_migration import *

# Test 1: Analyze
>>> test_analyze_transit_locations(env)

# Test 2: Transit migration
>>> test_populate_transit_layers(env)

# Test 3: Full migration
>>> test_full_migration(env)

# Test 4: Verify consistency
>>> test_verify_transit_consistency(env)
```

## Running Migration from UI

Create a server action for easy access from Odoo interface:

```python
# In Odoo shell
>>> from odoo.addons.stock_fifo_by_location.migrations import populate_location_id
>>> action = populate_location_id.create_migration_server_action(env)
>>> print(f"Server action created: {action.name}")
```

Then navigate to:
**Settings → Technical → Server Actions → Populate Location IDs for Valuation Layers**

## Troubleshooting

### Problem: Many Failed Layers

**Solution:**
1. Review failed layer IDs
2. Check if stock moves exist for those layers
3. Manually set location_id for layers without moves:

```python
# For layers without moves, use product's default location
failed_layers = env['stock.valuation.layer'].browse(failed_ids)
for layer in failed_layers:
    if not layer.stock_move_id:
        # Find product's default location
        default_loc = env['stock.location'].search([
            ('usage', '=', 'internal'),
            ('company_id', '=', layer.company_id.id)
        ], limit=1)
        if default_loc:
            layer.location_id = default_loc.id
```

### Problem: Inconsistent Transit Layers

**Solution:**
Run verification and fix inconsistencies:

```python
# Find inconsistent transit layers
transit_layers = env['stock.valuation.layer'].search([
    ('location_id.usage', '=', 'transit')
])

for layer in transit_layers:
    if not layer.stock_move_id:
        continue
    
    move = layer.stock_move_id
    
    # Fix based on quantity
    if layer.quantity > 0:
        # Positive: should use destination
        if layer.location_id != move.location_dest_id:
            layer.location_id = move.location_dest_id
    elif layer.quantity < 0:
        # Negative: should use source
        if layer.location_id != move.location_id:
            layer.location_id = move.location_id
```

### Problem: Migration Takes Too Long

**Solution:**
Process in batches:

```python
# Migrate in batches of 1000
batch_size = 1000
layers = env['stock.valuation.layer'].search([
    ('location_id', '=', False)
], limit=batch_size)

while layers:
    for layer in layers:
        # Migration logic here
        pass
    
    env.cr.commit()
    
    # Get next batch
    layers = env['stock.valuation.layer'].search([
        ('location_id', '=', False)
    ], limit=batch_size)
```

## Transit Location Best Practices

1. **Always use Transit locations for inter-warehouse transfers**
   - Don't directly transfer Internal → Internal between different warehouses
   - Use route: Warehouse A → Transit → Warehouse B

2. **Configure Transit locations properly**
   - Set correct company_id
   - Set proper parent location
   - Use descriptive names (e.g., "WH1 to WH2 Transit")

3. **Monitor valuation layers**
   - Regularly check for layers without location_id
   - Run periodic consistency checks
   - Review failed migrations

4. **Document custom flows**
   - If using custom stock flows, document them
   - Update migration script if needed
   - Test thoroughly in staging

## Migration Statistics

After migration, verify these key metrics:

```python
# Total layers
total = env['stock.valuation.layer'].search_count([])

# Layers with location
with_location = env['stock.valuation.layer'].search_count([
    ('location_id', '!=', False)
])

# Transit layers
transit = env['stock.valuation.layer'].search_count([
    ('location_id.usage', '=', 'transit')
])

# Internal layers
internal = env['stock.valuation.layer'].search_count([
    ('location_id.usage', '=', 'internal')
])

print(f"Total layers: {total}")
print(f"With location: {with_location} ({with_location/total*100:.1f}%)")
print(f"Transit: {transit}")
print(f"Internal: {internal}")
```

## Support

For issues or questions:
1. Review this guide thoroughly
2. Check the test script output
3. Review migration logs
4. Check failed layer IDs
5. Contact your Odoo administrator

## References

- Module documentation: `/opt/instance1/odoo17/custom-addons/stock_fifo_by_location/README.md`
- Transit location analysis: `TRANSIT_LOCATION_VALUATION_ANALYSIS.md`
- Migration script: `migrations/populate_location_id.py`
- Test script: `test_transit_migration.py`
