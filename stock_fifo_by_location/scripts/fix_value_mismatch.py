#!/usr/bin/env python3
"""
Fix Value Mismatch for Products with qty=0 but value≠0

Problem: Some products have total_qty = 0 but total_value ≠ 0
This happens when positive and negative layers don't balance in value.

Root cause: Before fixing _run_fifo(), cross-warehouse FIFO consumption
created negative layers with incorrect values.

Solution: Recalculate negative layer values to match positive layer values
consumed, ensuring total_value = 0 when total_qty = 0.
"""

import sys
import os

# Add Odoo to path
sys.path.append('/opt/instance1/odoo17')

import odoo
from odoo import api, SUPERUSER_ID

# Initialize Odoo
odoo.tools.config.parse_config([
    '-c', '/etc/instance1.conf',
    '-d', 'MOG_Test',
])

print("\n" + "="*80)
print("Fix Value Mismatch: Products with qty=0 but value≠0")
print("="*80)

registry = odoo.registry('MOG_Test')
with registry.cursor() as cr:
    env = api.Environment(cr, SUPERUSER_ID, {})
registry = odoo.registry('MOG_Test')
with registry.cursor() as cr:
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    # Find products with value mismatch
    query = """
        SELECT 
            pp.id as product_id,
            pp.default_code,
            pt.name,
            SUM(svl.quantity) as total_qty,
            SUM(svl.value) as total_value,
            SUM(svl.remaining_qty) as remaining_qty,
            SUM(svl.remaining_value) as remaining_value
        FROM stock_valuation_layer svl
        JOIN product_product pp ON pp.id = svl.product_id
        JOIN product_template pt ON pt.id = pp.product_tmpl_id
        GROUP BY pp.id, pp.default_code, pt.name
        HAVING ABS(SUM(svl.quantity)) < 0.01
           AND ABS(SUM(svl.value)) > 0.01
        ORDER BY ABS(SUM(svl.value)) DESC
    """
    
    cr.execute(query)
    products_with_issue = cr.fetchall()
    
    print(f"\nพบ {len(products_with_issue)} products ที่มีปัญหา")
    
    if not products_with_issue:
        print("✅ ไม่มี products ที่ต้องแก้ไข")
        sys.exit(0)
    
    print("\nTop 10 products with largest value mismatch:")
    for i, row in enumerate(products_with_issue[:10], 1):
        product_id, code, name, qty, value, rem_qty, rem_val = row
        print(f"{i:3d}. {code:15s} | Qty: {qty:8.2f} | Value: {value:12.2f}")
    
    # Ask for confirmation
    print("\n" + "-"*80)
    print("วิธีแก้ไข:")
    print("1. สำหรับแต่ละ product ที่มีปัญหา")
    print("2. คำนวณ total positive value และ total negative value")
    print("3. ปรับ negative layers ให้ balance กับ positive layers")
    print("4. โดย distribute value difference ตาม proportion ของแต่ละ negative layer")
    print("-"*80)
    
    response = input(f"\nต้องการแก้ไข {len(products_with_issue)} products? (yes/no): ")
    if response.lower() != 'yes':
        print("ยกเลิก")
        sys.exit(0)
    
    fixed_count = 0
    error_count = 0
    
    for row in products_with_issue:
        product_id, code, name, total_qty, total_value, rem_qty, rem_val = row
        
        try:
            # Get all layers for this product
            cr.execute("""
                SELECT 
                    id, 
                    quantity, 
                    value,
                    warehouse_id
                FROM stock_valuation_layer
                WHERE product_id = %s
                ORDER BY create_date, id
            """, (product_id,))
            
            layers = cr.fetchall()
            
            # Separate positive and negative
            positive_layers = [(lid, qty, val, wh) for lid, qty, val, wh in layers if qty > 0]
            negative_layers = [(lid, qty, val, wh) for lid, qty, val, wh in layers if qty < 0]
            
            positive_value = sum(val for _, _, val, _ in positive_layers)
            negative_value = sum(val for _, _, val, _ in negative_layers)
            
            value_diff = positive_value + negative_value  # Should be 0
            
            if abs(value_diff) < 0.01:
                continue
            
            # Distribute the difference across negative layers proportionally
            total_negative_qty = abs(sum(qty for _, qty, _, _ in negative_layers))
            
            if total_negative_qty < 0.01:
                # No negative layers to adjust, create a correction layer
                print(f"  ⚠️  {code}: No negative layers to adjust (diff: {value_diff:.2f})")
                continue
            
            for layer_id, qty, val, wh in negative_layers:
                proportion = abs(qty) / total_negative_qty
                adjustment = -value_diff * proportion
                new_value = val + adjustment
                
                cr.execute("""
                    UPDATE stock_valuation_layer
                    SET value = %s
                    WHERE id = %s
                """, (new_value, layer_id))
            
            fixed_count += 1
            print(f"  ✅ {code}: Fixed (diff: {value_diff:.2f} → 0.00)")
            
        except Exception as e:
            error_count += 1
            print(f"  ❌ {code}: Error - {e}")
    
    # Commit changes
    cr.commit()
    
    print("\n" + "="*80)
    print(f"สรุปผลการแก้ไข:")
    print(f"  ✅ แก้ไขสำเร็จ: {fixed_count} products")
    print(f"  ❌ แก้ไขไม่สำเร็จ: {error_count} products")
    print("="*80)
