#!/usr/bin/env python3
"""
Test script to verify FIFO consumption during delivery
Tests if delivery from warehouse A consumes from correct warehouse's FIFO queue
"""

import xmlrpc.client

# Connection settings
url = 'http://localhost:8069'
db = 'instance1'
username = 'admin'
password = 'admin'

# Connect to Odoo
common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
uid = common.authenticate(db, username, password, {})
models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')

print("=" * 80)
print("🧪 Testing FIFO Consumption During Delivery")
print("=" * 80)

# Find a product with FIFO costing
products = models.execute_kw(db, uid, password, 'product.product', 'search_read', 
    [[('type', '=', 'product')]], 
    {'fields': ['name', 'categ_id'], 'limit': 5})

print("\n📦 Available products:")
for p in products:
    print(f"  - {p['name']} (ID: {p['id']})")

# Get product category to check cost method
if products:
    product_id = products[0]['id']
    product_name = products[0]['name']
    
    # Get category
    categ = models.execute_kw(db, uid, password, 'product.category', 'read',
        [[products[0]['categ_id'][0]]], {'fields': ['property_cost_method']})
    
    print(f"\n✅ Using product: {product_name}")
    print(f"   Cost method: {categ[0].get('property_cost_method', 'N/A')}")
    
    # Find warehouses
    warehouses = models.execute_kw(db, uid, password, 'stock.warehouse', 'search_read',
        [[]], {'fields': ['name', 'code'], 'limit': 5})
    
    print(f"\n🏢 Available warehouses:")
    for wh in warehouses:
        print(f"  - {wh['name']} (ID: {wh['id']}, Code: {wh['code']})")
    
    if len(warehouses) >= 1:
        wh_id = warehouses[0]['id']
        wh_name = warehouses[0]['name']
        
        # Check current valuation layers for this product at this warehouse
        print(f"\n📊 Current valuation layers for {product_name} at {wh_name}:")
        
        layers = models.execute_kw(db, uid, password, 'stock.valuation.layer', 'search_read',
            [[('product_id', '=', product_id), ('warehouse_id', '=', wh_id)]],
            {'fields': ['quantity', 'remaining_qty', 'unit_cost', 'warehouse_id', 'create_date'],
             'order': 'create_date asc', 'limit': 10})
        
        if layers:
            total_remaining = sum(l['remaining_qty'] for l in layers)
            print(f"   Total remaining qty: {total_remaining}")
            for l in layers:
                wh_info = l.get('warehouse_id', [False, 'No Warehouse'])
                print(f"   - Layer {l['id']}: qty={l['quantity']:.2f}, "
                      f"remaining={l['remaining_qty']:.2f}, "
                      f"unit_cost={l['unit_cost']:.4f}, "
                      f"warehouse={wh_info[1] if wh_info else 'None'}")
        else:
            print("   ⚠️ No layers found!")
        
        # Check stock quant
        quants = models.execute_kw(db, uid, password, 'stock.quant', 'search_read',
            [[('product_id', '=', product_id), ('location_id.warehouse_id', '=', wh_id)]],
            {'fields': ['quantity', 'location_id'], 'limit': 5})
        
        print(f"\n📦 Stock quantity at {wh_name}:")
        total_qty = sum(q['quantity'] for q in quants)
        print(f"   Total: {total_qty}")
        for q in quants:
            print(f"   - {q['location_id'][1]}: {q['quantity']:.2f}")
        
        print("\n" + "=" * 80)
        print("✅ Analysis complete!")
        print("\nTo test delivery:")
        print(f"1. Create a sales order for product '{product_name}'")
        print(f"2. Set warehouse to '{wh_name}'")
        print("3. Confirm and deliver")
        print("4. Check if FIFO consumed from correct warehouse")
        print("5. Monitor logs for: '🔍 _run_fifo() for Layer' messages")
        print("=" * 80)
    else:
        print("\n⚠️ Need at least 1 warehouse")
else:
    print("\n⚠️ No products found!")
