#!/usr/bin/env python3
"""
Test script to verify FIFO consumption fix for delivery
Tests that delivery from warehouse A consumes ONLY from warehouse A's FIFO queue
"""

import xmlrpc.client
from datetime import datetime

# Connection settings
url = 'http://localhost:8069'
db = 'instance1'
username = 'admin'
password = 'admin'

# Connect to Odoo
common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
uid = common.authenticate(db, username, password, {})
models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')

print("=" * 100)
print("🧪 TEST: Verify FIFO Consumption During Delivery from Correct Warehouse")
print("=" * 100)

# Find test product with FIFO costing
products = models.execute_kw(db, uid, password, 'product.product', 'search_read',
    [[('type', '=', 'product'), ('categ_id.property_cost_method', '=', 'fifo')]],
    {'fields': ['name', 'categ_id', 'standard_price'], 'limit': 1})

if not products:
    print("\n❌ No FIFO products found! Please set a product category to use FIFO costing.")
    exit(1)

product_id = products[0]['id']
product_name = products[0]['name']

print(f"\n✅ Test Product: {product_name} (ID: {product_id})")

# Find warehouses (need at least 2)
warehouses = models.execute_kw(db, uid, password, 'stock.warehouse', 'search_read',
    [[]], {'fields': ['name', 'code'], 'limit': 5})

if len(warehouses) < 2:
    print(f"\n❌ Need at least 2 warehouses for proper testing. Found: {len(warehouses)}")
    exit(1)

wh_a = warehouses[0]
wh_b = warehouses[1]

print(f"\n🏢 Warehouse A: {wh_a['name']} (ID: {wh_a['id']})")
print(f"🏢 Warehouse B: {wh_b['name']} (ID: {wh_b['id']})")

# Function to get valuation layers
def get_layers(product_id, warehouse_id):
    return models.execute_kw(db, uid, password, 'stock.valuation.layer', 'search_read',
        [[('product_id', '=', product_id), ('warehouse_id', '=', warehouse_id)]],
        {'fields': ['quantity', 'remaining_qty', 'unit_cost', 'warehouse_id', 'create_date', 'description'],
         'order': 'create_date asc'})

# Check initial state
print("\n" + "="*100)
print("📊 INITIAL STATE")
print("="*100)

layers_a = get_layers(product_id, wh_a['id'])
layers_b = get_layers(product_id, wh_b['id'])

print(f"\nWarehouse A ({wh_a['name']}):")
if layers_a:
    total_remaining_a = sum(l['remaining_qty'] for l in layers_a)
    print(f"  Total remaining qty: {total_remaining_a}")
    for l in layers_a:
        print(f"  - Layer {l['id']}: qty={l['quantity']:.2f}, remaining={l['remaining_qty']:.2f}, "
              f"cost={l['unit_cost']:.4f}")
else:
    print("  ⚠️ No layers")

print(f"\nWarehouse B ({wh_b['name']}):")
if layers_b:
    total_remaining_b = sum(l['remaining_qty'] for l in layers_b)
    print(f"  Total remaining qty: {total_remaining_b}")
    for l in layers_b:
        print(f"  - Layer {l['id']}: qty={l['quantity']:.2f}, remaining={l['remaining_qty']:.2f}, "
              f"cost={l['unit_cost']:.4f}")
else:
    print("  ⚠️ No layers")

# Check stock quantity
quants_a = models.execute_kw(db, uid, password, 'stock.quant', 'search_read',
    [[('product_id', '=', product_id), ('location_id.warehouse_id', '=', wh_a['id'])]],
    {'fields': ['quantity']})
stock_a = sum(q['quantity'] for q in quants_a)

quants_b = models.execute_kw(db, uid, password, 'stock.quant', 'search_read',
    [[('product_id', '=', product_id), ('location_id.warehouse_id', '=', wh_b['id'])]],
    {'fields': ['quantity']})
stock_b = sum(q['quantity'] for q in quants_b)

print(f"\n📦 Stock Quantities:")
print(f"  Warehouse A: {stock_a}")
print(f"  Warehouse B: {stock_b}")

# Determine which warehouse to test
test_wh = wh_a if stock_a > 0 else wh_b if stock_b > 0 else None

if not test_wh:
    print("\n⚠️ No stock in either warehouse!")
    print("\nTo run this test:")
    print("1. Receive some stock into Warehouse A or B")
    print("2. Run this test again")
    exit(0)

test_wh_id = test_wh['id']
test_wh_name = test_wh['name']
test_qty = min(1.0, stock_a if test_wh_id == wh_a['id'] else stock_b)

print("\n" + "="*100)
print(f"🎯 TEST SCENARIO: Deliver {test_qty} unit(s) from {test_wh_name}")
print("="*100)

# Get initial remaining qty
initial_layers = get_layers(product_id, test_wh_id)
initial_remaining = sum(l['remaining_qty'] for l in initial_layers if l['remaining_qty'] > 0)
print(f"\n📊 Before delivery: {test_wh_name} has {initial_remaining} units in FIFO queue")

# Find customer location
customer_locations = models.execute_kw(db, uid, password, 'stock.location', 'search',
    [[('usage', '=', 'customer')]], {'limit': 1})

if not customer_locations:
    print("\n❌ No customer location found!")
    exit(1)

customer_loc_id = customer_locations[0]

# Get stock location for test warehouse
stock_location = models.execute_kw(db, uid, password, 'stock.location', 'search_read',
    [[('warehouse_id', '=', test_wh_id), ('usage', '=', 'internal')]],
    {'fields': ['name'], 'limit': 1})

if not stock_location:
    print(f"\n❌ No internal location found for {test_wh_name}!")
    exit(1)

source_loc_id = stock_location[0]['id']

print(f"\n🚚 Creating delivery move...")
print(f"   From: {stock_location[0]['name']} (Warehouse: {test_wh_name})")
print(f"   To: Customer")
print(f"   Qty: {test_qty}")

# Create picking (delivery order)
picking_type = models.execute_kw(db, uid, password, 'stock.picking.type', 'search',
    [[('warehouse_id', '=', test_wh_id), ('code', '=', 'outgoing')]], {'limit': 1})

if not picking_type:
    print(f"\n❌ No outgoing picking type found for {test_wh_name}!")
    exit(1)

picking_id = models.execute_kw(db, uid, password, 'stock.picking', 'create', [{
    'picking_type_id': picking_type[0],
    'location_id': source_loc_id,
    'location_dest_id': customer_loc_id,
    'move_ids_without_package': [(0, 0, {
        'name': f'TEST Delivery {product_name}',
        'product_id': product_id,
        'product_uom_qty': test_qty,
        'product_uom': products[0].get('uom_id', [1])[0] if 'uom_id' in products[0] else 1,
        'location_id': source_loc_id,
        'location_dest_id': customer_loc_id,
    })]
}])

print(f"✅ Created picking ID: {picking_id}")

# Confirm picking
models.execute_kw(db, uid, password, 'stock.picking', 'action_confirm', [[picking_id]])
print(f"✅ Confirmed picking")

# Validate picking (this triggers FIFO consumption)
print(f"\n⏳ Validating picking (this triggers FIFO consumption)...")
print(f"   📝 Check logs for: '🔍 _run_fifo() for Layer' and '📥 Consuming from Layer'")

try:
    models.execute_kw(db, uid, password, 'stock.picking', 'button_validate', [[picking_id]])
    print(f"✅ Validated picking")
except Exception as e:
    print(f"⚠️ Validation error (may need manual intervention): {e}")

# Check results
print("\n" + "="*100)
print("📊 RESULTS AFTER DELIVERY")
print("="*100)

# Get layers after delivery
final_layers_a = get_layers(product_id, wh_a['id'])
final_layers_b = get_layers(product_id, wh_b['id'])

print(f"\nWarehouse A ({wh_a['name']}):")
if final_layers_a:
    total_remaining_a = sum(l['remaining_qty'] for l in final_layers_a if l['remaining_qty'] > 0)
    print(f"  Total remaining qty: {total_remaining_a}")
    for l in final_layers_a[-3:]:  # Show last 3 layers
        print(f"  - Layer {l['id']}: qty={l['quantity']:.2f}, remaining={l['remaining_qty']:.2f}, "
              f"cost={l['unit_cost']:.4f}")
        if l.get('description'):
            print(f"    Description: {l['description']}")
else:
    print("  No layers")

print(f"\nWarehouse B ({wh_b['name']}):")
if final_layers_b:
    total_remaining_b = sum(l['remaining_qty'] for l in final_layers_b if l['remaining_qty'] > 0)
    print(f"  Total remaining qty: {total_remaining_b}")
    for l in final_layers_b[-3:]:  # Show last 3 layers
        print(f"  - Layer {l['id']}: qty={l['quantity']:.2f}, remaining={l['remaining_qty']:.2f}, "
              f"cost={l['unit_cost']:.4f}")
        if l.get('description'):
            print(f"    Description: {l['description']}")
else:
    print("  No layers")

# Verification
print("\n" + "="*100)
print("✅ VERIFICATION")
print("="*100)

# Check which warehouse's layers were consumed
if test_wh_id == wh_a['id']:
    expected_remaining = initial_remaining - test_qty
    actual_remaining = sum(l['remaining_qty'] for l in final_layers_a if l['remaining_qty'] > 0)
    
    print(f"\n✓ Expected: Warehouse A remaining_qty should decrease by {test_qty}")
    print(f"  Initial: {initial_remaining}")
    print(f"  Expected after: {expected_remaining}")
    print(f"  Actual after: {actual_remaining}")
    
    if abs(actual_remaining - expected_remaining) < 0.01:
        print(f"  ✅ PASS: Warehouse A FIFO queue consumed correctly")
    else:
        print(f"  ❌ FAIL: Warehouse A FIFO queue not consumed correctly")
    
    # Check that Warehouse B was not affected
    initial_remaining_b = sum(l['remaining_qty'] for l in layers_b if l['remaining_qty'] > 0)
    final_remaining_b = sum(l['remaining_qty'] for l in final_layers_b if l['remaining_qty'] > 0)
    
    print(f"\n✓ Expected: Warehouse B remaining_qty should NOT change")
    print(f"  Initial: {initial_remaining_b}")
    print(f"  Final: {final_remaining_b}")
    
    if abs(final_remaining_b - initial_remaining_b) < 0.01:
        print(f"  ✅ PASS: Warehouse B not affected")
    else:
        print(f"  ❌ FAIL: Warehouse B was incorrectly consumed!")

else:
    # Test was on Warehouse B
    expected_remaining = initial_remaining - test_qty
    actual_remaining = sum(l['remaining_qty'] for l in final_layers_b if l['remaining_qty'] > 0)
    
    print(f"\n✓ Expected: Warehouse B remaining_qty should decrease by {test_qty}")
    print(f"  Initial: {initial_remaining}")
    print(f"  Expected after: {expected_remaining}")
    print(f"  Actual after: {actual_remaining}")
    
    if abs(actual_remaining - expected_remaining) < 0.01:
        print(f"  ✅ PASS: Warehouse B FIFO queue consumed correctly")
    else:
        print(f"  ❌ FAIL: Warehouse B FIFO queue not consumed correctly")
    
    # Check that Warehouse A was not affected
    initial_remaining_a = sum(l['remaining_qty'] for l in layers_a if l['remaining_qty'] > 0)
    final_remaining_a = sum(l['remaining_qty'] for l in final_layers_a if l['remaining_qty'] > 0)
    
    print(f"\n✓ Expected: Warehouse A remaining_qty should NOT change")
    print(f"  Initial: {initial_remaining_a}")
    print(f"  Final: {final_remaining_a}")
    
    if abs(final_remaining_a - initial_remaining_a) < 0.01:
        print(f"  ✅ PASS: Warehouse A not affected")
    else:
        print(f"  ❌ FAIL: Warehouse A was incorrectly consumed!")

print("\n" + "="*100)
print("📝 CHECK ODOO LOGS")
print("="*100)
print("\nLook for these log entries in Odoo logs:")
print("1. '🏭 _create_out_svl for move' - Shows which warehouse was identified")
print("2. '🔍 _run_fifo() for Layer' - Shows which warehouse's FIFO queue is being searched")
print("3. '📥 Consuming from Layer X at warehouse Y' - Shows which layers were consumed")
print("\nIf delivery consumed from wrong warehouse, you will see:")
print("  - '🔍 _run_fifo()' searching Warehouse A")
print("  - '📥 Consuming from Layer' showing Warehouse B")
print("\nWith the fix, warehouse should be consistent in all log entries!")
print("="*100)
