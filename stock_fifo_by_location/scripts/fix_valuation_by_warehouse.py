#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script สำหรับแก้ไข Stock Valuation Layer ให้ถูกต้องตาม Warehouse

ใช้สำหรับกรณี: ยกของเข้าคลังแล้วข้อมูล valuation ผิด หรือ remaining qty ไม่ตรงกับ moved qty

วิธีใช้:
1. รันผ่าน Odoo shell:
   python3 odoo-bin shell -d MOG_TEST --no-http < fix_valuation_by_warehouse.py

2. หรือ copy code ไป paste ใน Odoo shell

การทำงาน:
- วิเคราะห์ stock.move และ stock.valuation.layer ทั้งหมด
- ตรวจสอบว่า warehouse_id ถูกต้องหรือไม่
- แก้ไข remaining_qty และ remaining_value ให้ถูกต้องตาม warehouse
- คำนวณ FIFO ใหม่แยกตาม warehouse
"""

import logging
from datetime import datetime

_logger = logging.getLogger(__name__)

def fix_valuation_by_warehouse(env, dry_run=True):
    """
    แก้ไข valuation layer ให้ถูกต้องตาม warehouse
    
    Args:
        env: Odoo environment
        dry_run: ถ้า True จะไม่บันทึกข้อมูล แค่แสดงผล (default: True)
    """
    print("\n" + "="*80)
    print("Script แก้ไข Stock Valuation Layer ตาม Warehouse")
    print("="*80)
    print(f"โหมด: {'DRY RUN (ไม่บันทึกข้อมูล)' if dry_run else 'LIVE (บันทึกข้อมูลจริง)'}")
    print(f"เวลาเริ่มต้น: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    
    SVL = env['stock.valuation.layer']
    StockMove = env['stock.move']
    Warehouse = env['stock.warehouse']
    Product = env['product.product']
    
    # สถิติ
    stats = {
        'total_layers': 0,
        'fixed_warehouse': 0,
        'fixed_remaining': 0,
        'errors': 0,
        'warehouses_processed': set(),
    }
    
    # ขั้นตอนที่ 1: แก้ไข warehouse_id ที่ขาดหายหรือผิด
    print("\n" + "-"*80)
    print("ขั้นตอนที่ 1: ตรวจสอบและแก้ไข warehouse_id")
    print("-"*80)
    
    layers_without_wh = SVL.search([('warehouse_id', '=', False)])
    print(f"พบ valuation layer ที่ไม่มี warehouse_id: {len(layers_without_wh)} รายการ")
    
    for layer in layers_without_wh:
        stats['total_layers'] += 1
        
        if not layer.stock_move_id:
            print(f"  ⚠️ Layer {layer.id}: ไม่มี stock_move_id ข้ามไป")
            stats['errors'] += 1
            continue
        
        move = layer.stock_move_id
        product = layer.product_id
        quantity = layer.quantity
        
        # หา warehouse ที่ถูกต้อง
        target_wh = None
        
        if quantity > 0:
            # Positive layer (เข้า) -> ใช้ destination warehouse
            if move.location_dest_id and move.location_dest_id.warehouse_id:
                target_wh = move.location_dest_id.warehouse_id
        else:
            # Negative layer (ออก) -> ใช้ source warehouse
            if move.location_id and move.location_id.warehouse_id:
                target_wh = move.location_id.warehouse_id
        
        if target_wh:
            print(f"  ✓ Layer {layer.id}: Product={product.default_code}, "
                  f"Qty={quantity:,.2f}, จะตั้ง WH={target_wh.name}")
            
            if not dry_run:
                layer.warehouse_id = target_wh.id
            
            stats['fixed_warehouse'] += 1
            stats['warehouses_processed'].add(target_wh.id)
        else:
            print(f"  ⚠️ Layer {layer.id}: ไม่สามารถหา warehouse ได้")
            stats['errors'] += 1
    
    # ขั้นตอนที่ 2: คำนวณ remaining_qty และ remaining_value ใหม่แยกตาม warehouse
    print("\n" + "-"*80)
    print("ขั้นตอนที่ 2: คำนวณ remaining_qty และ remaining_value ใหม่")
    print("-"*80)
    
    # หา product ทั้งหมดที่มี valuation layer
    products_with_layers = SVL.search([]).mapped('product_id')
    print(f"พบสินค้าที่มี valuation layer: {len(products_with_layers)} รายการ")
    
    # หา warehouse ทั้งหมด
    warehouses = Warehouse.search([])
    print(f"พบ warehouse: {len(warehouses)} คลัง")
    
    for warehouse in warehouses:
        print(f"\n  กำลังประมวลผล: {warehouse.name}")
        
        for product in products_with_layers:
            # หา layers ทั้งหมดของ product+warehouse นี้ เรียงตามวันที่
            layers = SVL.search([
                ('product_id', '=', product.id),
                ('warehouse_id', '=', warehouse.id),
            ], order='create_date ASC, id ASC')
            
            if not layers:
                continue
            
            # คำนวณ FIFO
            remaining_qty = 0.0
            remaining_value = 0.0
            fifo_queue = []  # [(qty, unit_cost, layer_id)]
            
            layers_updated = 0
            
            for layer in layers:
                old_remain_qty = layer.remaining_qty
                old_remain_value = layer.remaining_value
                
                if layer.quantity > 0:
                    # Positive layer (เข้า) - เพิ่มเข้า FIFO queue
                    remaining_qty += layer.quantity
                    remaining_value += layer.value
                    
                    # เพิ่มเข้า queue
                    fifo_queue.append({
                        'qty': layer.quantity,
                        'unit_cost': layer.unit_cost,
                        'layer_id': layer.id,
                        'remaining': layer.quantity,
                    })
                    
                    # อัปเดต remaining ของ layer นี้
                    new_remain_qty = layer.quantity
                    new_remain_value = layer.value
                    
                else:
                    # Negative layer (ออก) - ตัดจาก FIFO queue
                    qty_to_consume = abs(layer.quantity)
                    value_consumed = 0.0
                    
                    # ตัดจาก queue (FIFO)
                    while qty_to_consume > 0.001 and fifo_queue:
                        oldest = fifo_queue[0]
                        
                        if oldest['remaining'] <= qty_to_consume:
                            # ใช้หมดชั้นนี้
                            qty_used = oldest['remaining']
                            value_used = qty_used * oldest['unit_cost']
                            
                            qty_to_consume -= qty_used
                            value_consumed += value_used
                            remaining_qty -= qty_used
                            remaining_value -= value_used
                            
                            fifo_queue.pop(0)
                        else:
                            # ใช้บางส่วน
                            qty_used = qty_to_consume
                            value_used = qty_used * oldest['unit_cost']
                            
                            oldest['remaining'] -= qty_used
                            value_consumed += value_used
                            remaining_qty -= qty_used
                            remaining_value -= value_used
                            
                            qty_to_consume = 0
                    
                    # อัปเดต remaining ของ layer นี้ (negative layer ไม่มี remaining)
                    new_remain_qty = 0.0
                    new_remain_value = 0.0
                
                # ตรวจสอบว่ามีการเปลี่ยนแปลงหรือไม่
                if abs(old_remain_qty - new_remain_qty) > 0.01 or abs(old_remain_value - new_remain_value) > 0.01:
                    print(f"    Layer {layer.id}: {product.default_code} "
                          f"Qty={layer.quantity:,.2f}, "
                          f"Remain: {old_remain_qty:,.2f} → {new_remain_qty:,.2f}, "
                          f"Value: {old_remain_value:,.2f} → {new_remain_value:,.2f}")
                    
                    if not dry_run:
                        layer.write({
                            'remaining_qty': new_remain_qty,
                            'remaining_value': new_remain_value,
                        })
                    
                    layers_updated += 1
                    stats['fixed_remaining'] += 1
            
            if layers_updated > 0:
                print(f"    ✓ {product.default_code}: อัปเดต {layers_updated} layers")
    
    # สรุปผล
    print("\n" + "="*80)
    print("สรุปผลการทำงาน")
    print("="*80)
    print(f"Total layers ตรวจสอบ: {stats['total_layers']:,}")
    print(f"แก้ไข warehouse_id: {stats['fixed_warehouse']:,} รายการ")
    print(f"แก้ไข remaining_qty/value: {stats['fixed_remaining']:,} รายการ")
    print(f"Warehouse ที่ประมวลผล: {len(stats['warehouses_processed'])} คลัง")
    print(f"Errors: {stats['errors']:,}")
    print(f"เวลาสิ้นสุด: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    if dry_run:
        print("\n⚠️ นี่คือ DRY RUN ข้อมูลยังไม่ถูกบันทึก")
        print("ถ้าต้องการบันทึกจริง ให้เรียก: fix_valuation_by_warehouse(env, dry_run=False)")
    else:
        print("\n✅ บันทึกข้อมูลเรียบร้อยแล้ว")
        
        # Commit ถ้าไม่ใช่ dry_run
        env.cr.commit()
        print("✅ Commit database เรียบร้อย")
    
    print("="*80 + "\n")
    
    return stats


# ===============================================================================
# การใช้งาน
# ===============================================================================

if __name__ == '__main__':
    # เรียกใช้ใน Odoo shell
    print("\nเริ่มต้นการทำงาน...")
    
    # ขั้นตอนที่ 1: ทดสอบก่อน (DRY RUN)
    print("\n" + "="*80)
    print("ขั้นตอนที่ 1: ทดสอบก่อน (DRY RUN)")
    print("="*80)
    stats = fix_valuation_by_warehouse(env, dry_run=True)
    
    # ถามผู้ใช้ว่าต้องการดำเนินการจริงหรือไม่
    print("\n" + "="*80)
    print("ต้องการดำเนินการจริงหรือไม่?")
    print("="*80)
    print("ถ้าต้องการ ให้รันคำสั่ง:")
    print("  fix_valuation_by_warehouse(env, dry_run=False)")
    print("="*80)

else:
    # ถ้า import ใน Odoo shell
    print("\n✅ โหลด script เรียบร้อย")
    print("\nคำสั่งที่ใช้ได้:")
    print("  1. ทดสอบ (ไม่บันทึก):   fix_valuation_by_warehouse(env, dry_run=True)")
    print("  2. ดำเนินการจริง:        fix_valuation_by_warehouse(env, dry_run=False)")
    print()
