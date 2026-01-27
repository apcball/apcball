#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script สำหรับสร้าง Stock เริ่มต้นแยกตาม Warehouse

ใช้สำหรับ: ยกของเข้าคลังครั้งแรก หรือ ปรับปรุงยอดคงเหลือให้ถูกต้อง

วิธีใช้:
1. เตรียมข้อมูลใน Excel/CSV: Product Code, Warehouse, Quantity, Unit Cost
2. รันผ่าน Odoo shell:
   python3 odoo-bin shell -d MOG_TEST --no-http < create_initial_stock_by_warehouse.py

3. หรือ copy function ไป paste ใน Odoo shell แล้วเรียกใช้ตามตัวอย่าง
"""

import logging
from datetime import datetime

_logger = logging.getLogger(__name__)


def create_initial_stock_layer(env, product_code, warehouse_code, quantity, unit_cost, 
                                description='ยกยอดเข้าระบบ', dry_run=True):
    """
    สร้าง valuation layer เริ่มต้นสำหรับสินค้าในคลัง
    
    Args:
        env: Odoo environment
        product_code: รหัสสินค้า (default_code)
        warehouse_code: รหัสคลัง (code)
        quantity: จำนวน (บวก)
        unit_cost: ราคาต้นทุนต่อหน่วย
        description: คำอธิบาย
        dry_run: ทดสอบไม่บันทึก (default: True)
    
    Returns:
        dict: ผลลัพธ์การสร้าง layer
    """
    Product = env['product.product']
    Warehouse = env['stock.warehouse']
    SVL = env['stock.valuation.layer']
    StockMove = env['stock.move']
    
    # หาสินค้า
    product = Product.search([('default_code', '=', product_code)], limit=1)
    if not product:
        return {
            'success': False,
            'error': f'ไม่พบสินค้า: {product_code}'
        }
    
    # หาคลัง
    warehouse = Warehouse.search([('code', '=', warehouse_code)], limit=1)
    if not warehouse:
        return {
            'success': False,
            'error': f'ไม่พบคลัง: {warehouse_code}'
        }
    
    # ตรวจสอบค่า
    if quantity <= 0:
        return {
            'success': False,
            'error': f'จำนวนต้องมากกว่า 0: {quantity}'
        }
    
    if unit_cost < 0:
        return {
            'success': False,
            'error': f'ราคาต้นทุนต้องไม่เป็นลบ: {unit_cost}'
        }
    
    # คำนวณมูลค่า
    value = quantity * unit_cost
    
    result = {
        'success': True,
        'product': product.display_name,
        'product_code': product_code,
        'warehouse': warehouse.name,
        'warehouse_code': warehouse_code,
        'quantity': quantity,
        'unit_cost': unit_cost,
        'value': value,
        'description': description,
    }
    
    if not dry_run:
        # สร้าง stock move สำหรับ Inventory Adjustment
        inventory_location = env.ref('stock.location_inventory')
        stock_location = warehouse.lot_stock_id
        
        move_vals = {
            'name': f'ยกยอด: {product.display_name}',
            'product_id': product.id,
            'product_uom': product.uom_id.id,
            'product_uom_qty': quantity,
            'location_id': inventory_location.id,
            'location_dest_id': stock_location.id,
            'state': 'done',
            'company_id': warehouse.company_id.id,
        }
        
        move = StockMove.create(move_vals)
        
        # สร้าง valuation layer
        layer_vals = {
            'stock_move_id': move.id,
            'product_id': product.id,
            'warehouse_id': warehouse.id,
            'quantity': quantity,
            'unit_cost': unit_cost,
            'value': value,
            'remaining_qty': quantity,
            'remaining_value': value,
            'description': description,
            'company_id': warehouse.company_id.id,
        }
        
        layer = SVL.create(layer_vals)
        
        result['move_id'] = move.id
        result['layer_id'] = layer.id
        
        # Commit
        env.cr.commit()
    
    return result


def bulk_create_initial_stock(env, stock_data, dry_run=True):
    """
    สร้าง stock เริ่มต้นจากข้อมูลหลายรายการ
    
    Args:
        env: Odoo environment
        stock_data: list of dict [
            {
                'product_code': 'PROD001',
                'warehouse_code': 'WH1',
                'quantity': 100,
                'unit_cost': 50.00,
                'description': 'ยกยอดเริ่มต้น'
            },
            ...
        ]
        dry_run: ทดสอบไม่บันทึก (default: True)
    
    Returns:
        dict: สรุปผลการสร้าง
    """
    print("\n" + "="*80)
    print("Bulk Create Initial Stock by Warehouse")
    print("="*80)
    print(f"โหมด: {'DRY RUN (ไม่บันทึก)' if dry_run else 'LIVE (บันทึกจริง)'}")
    print(f"รายการทั้งหมด: {len(stock_data)}")
    print(f"เวลา: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    
    results = {
        'total': len(stock_data),
        'success': 0,
        'failed': 0,
        'errors': [],
        'details': []
    }
    
    for idx, data in enumerate(stock_data, 1):
        print(f"\n[{idx}/{len(stock_data)}] กำลังประมวลผล: "
              f"{data.get('product_code')} @ {data.get('warehouse_code')}")
        
        try:
            result = create_initial_stock_layer(
                env,
                product_code=data.get('product_code'),
                warehouse_code=data.get('warehouse_code'),
                quantity=data.get('quantity', 0),
                unit_cost=data.get('unit_cost', 0),
                description=data.get('description', 'ยกยอดเข้าระบบ'),
                dry_run=dry_run
            )
            
            if result['success']:
                results['success'] += 1
                print(f"  ✓ สำเร็จ: {result['product']} @ {result['warehouse']}")
                print(f"    จำนวน: {result['quantity']:,.2f} @ {result['unit_cost']:,.2f} "
                      f"= {result['value']:,.2f}")
            else:
                results['failed'] += 1
                results['errors'].append({
                    'row': idx,
                    'data': data,
                    'error': result.get('error')
                })
                print(f"  ✗ ล้มเหลว: {result.get('error')}")
            
            results['details'].append(result)
            
        except Exception as e:
            results['failed'] += 1
            error_msg = str(e)
            results['errors'].append({
                'row': idx,
                'data': data,
                'error': error_msg
            })
            print(f"  ✗ Exception: {error_msg}")
    
    # สรุปผล
    print("\n" + "="*80)
    print("สรุปผลการทำงาน")
    print("="*80)
    print(f"Total: {results['total']:,} รายการ")
    print(f"Success: {results['success']:,} รายการ")
    print(f"Failed: {results['failed']:,} รายการ")
    
    if results['errors']:
        print(f"\nรายการที่ล้มเหลว:")
        for error in results['errors']:
            print(f"  - Row {error['row']}: {error['error']}")
    
    if dry_run:
        print("\n⚠️ นี่คือ DRY RUN ข้อมูลยังไม่ถูกบันทึก")
    else:
        print("\n✅ บันทึกข้อมูลเรียบร้อยแล้ว")
    
    print("="*80 + "\n")
    
    return results


# ===============================================================================
# ตัวอย่างการใช้งาน
# ===============================================================================

def example_usage(env):
    """ตัวอย่างการใช้งาน"""
    
    print("\n" + "="*80)
    print("ตัวอย่างการใช้งาน")
    print("="*80)
    
    # ตัวอย่าง 1: สร้างรายการเดียว
    print("\n--- ตัวอย่าง 1: สร้างรายการเดียว ---")
    print("""
result = create_initial_stock_layer(
    env,
    product_code='PROD001',
    warehouse_code='WH/Stock',
    quantity=100,
    unit_cost=50.00,
    description='ยกยอดเข้าระบบ',
    dry_run=True  # เปลี่ยนเป็น False เมื่อต้องการบันทึกจริง
)
print(result)
    """)
    
    # ตัวอย่าง 2: สร้างหลายรายการ
    print("\n--- ตัวอย่าง 2: สร้างหลายรายการ ---")
    print("""
stock_data = [
    {
        'product_code': 'PROD001',
        'warehouse_code': 'WH/Stock',
        'quantity': 100,
        'unit_cost': 50.00,
        'description': 'ยกยอดเริ่มต้น คลังหลัก'
    },
    {
        'product_code': 'PROD001',
        'warehouse_code': 'WH2',
        'quantity': 50,
        'unit_cost': 50.00,
        'description': 'ยกยอดเริ่มต้น คลังสาขา'
    },
    {
        'product_code': 'PROD002',
        'warehouse_code': 'WH/Stock',
        'quantity': 200,
        'unit_cost': 30.00,
        'description': 'ยกยอดเริ่มต้น'
    },
]

results = bulk_create_initial_stock(env, stock_data, dry_run=True)
print(f"Success: {results['success']}, Failed: {results['failed']}")
    """)
    
    # ตัวอย่าง 3: อ่านจาก CSV
    print("\n--- ตัวอย่าง 3: อ่านจาก CSV (ต้อง import csv ก่อน) ---")
    print("""
import csv

def load_from_csv(filepath):
    stock_data = []
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            stock_data.append({
                'product_code': row['product_code'],
                'warehouse_code': row['warehouse_code'],
                'quantity': float(row['quantity']),
                'unit_cost': float(row['unit_cost']),
                'description': row.get('description', 'ยกยอดเข้าระบบ')
            })
    return stock_data

# ใช้งาน
stock_data = load_from_csv('/path/to/initial_stock.csv')
results = bulk_create_initial_stock(env, stock_data, dry_run=True)
    """)
    
    print("\n" + "="*80)


if __name__ == '__main__':
    # แสดงตัวอย่างการใช้งาน
    example_usage(env)

else:
    # ถ้า import ใน Odoo shell
    print("\n✅ โหลด script เรียบร้อย")
    print("\nฟังก์ชันที่ใช้ได้:")
    print("  1. สร้างรายการเดียว:     create_initial_stock_layer()")
    print("  2. สร้างหลายรายการ:       bulk_create_initial_stock()")
    print("  3. ดูตัวอย่าง:            example_usage(env)")
    print()
