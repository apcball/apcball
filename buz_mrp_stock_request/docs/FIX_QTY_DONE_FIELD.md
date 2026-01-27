# แก้ไข: Invalid field 'qty_done' on model 'stock.move.line'

## ปัญหา

เมื่อทำ Allocation (จัดสรร materials ให้ MO) เกิด error:
```
ValueError: Invalid field 'qty_done' on model 'stock.move.line'
```

## สาเหตุ

ใน **Odoo 17**, `stock.move.line` ไม่มี field `qty_done` แล้ว  
ต้องใช้ field `quantity` แทน

### Field Changes in Odoo 17
| Odoo 16 | Odoo 17 |
|---------|---------|
| `qty_done` | `quantity` |
| `reserved_qty` | `reserved_uom_qty` |

## การแก้ไข

**File**: `wizards/mrp_stock_request_allocate_wizard.py`  
**Method**: `_perform_consumption()`

### เปลี่ยนจาก:
```python
move_line_vals = {
    'move_id': raw_move.id,
    'product_id': product.id,
    'product_uom_id': raw_move.product_uom.id,
    'qty_done': qty_in_move_uom,  # ❌ Field เก่า
    'lot_id': lot.id,
    'location_id': location_src.id,
    'location_dest_id': raw_move.location_dest_id.id,
    'company_id': mo.company_id.id,
}
```

### เป็น:
```python
move_line_vals = {
    'move_id': raw_move.id,
    'product_id': product.id,
    'product_uom_id': raw_move.product_uom.id,
    'quantity': qty_in_move_uom,  # ✅ Field ใหม่
    'lot_id': lot.id,
    'location_id': location_src.id,
    'location_dest_id': raw_move.location_dest_id.id,
    'company_id': mo.company_id.id,
}
```

## ตำแหน่งที่แก้ไข

ใน method `_perform_consumption()` มี 2 จุด:

1. **บรรทัด ~317**: สำหรับ with lot/serial
2. **บรรทัด ~330**: สำหรับ without lot/serial

ทั้งสองจุดเปลี่ยนจาก `'qty_done'` → `'quantity'`

## ผลลัพธ์

✅ สามารถสร้าง stock.move.line ได้สำเร็จ  
✅ Allocation wizard ทำงานได้ปกติ  
✅ Consumed quantity บันทึกเข้า MO ถูกต้อง  

## การทดสอบ

### Test Case: Allocate Materials to MO

**ขั้นตอน**:
1. สร้าง Stock Request จาก MO
2. Confirm → Create picking
3. Validate picking (issue materials)
4. กดปุ่ม "Allocate to MO"
5. เลือก MO และระบุ quantity
6. Confirm allocation

**ผลลัพธ์ที่คาดหวัง**:
- ✅ ไม่มี error เกี่ยวกับ qty_done
- ✅ stock.move.line ถูกสร้างด้วย quantity ที่ระบุ
- ✅ MO แสดง consumed quantity ถูกต้อง
- ✅ Allocation record ถูกบันทึก

**ผลการทดสอบ**: ✅ Pass

## หมายเหตุเพิ่มเติม

### stock.move.line Fields ใน Odoo 17

**Quantity Fields**:
- `quantity`: จำนวนที่ทำจริง (done quantity) - **ใช้ตัวนี้**
- `reserved_uom_qty`: จำนวนที่ reserve ไว้
- `product_uom_qty`: จำนวนที่ต้องการ (planned)

**สำคัญ**: 
- `quantity` เป็น field ที่ใช้แทน `qty_done` จาก Odoo 16
- เมื่อ move line มี `quantity` > 0, move จะคำนวณ `quantity` (consumed) อัตโนมัติ

### Related Changes in Module

การแก้ไขนี้สอดคล้องกับการแก้ไขก่อนหน้าใน:
1. `models/mrp_stock_request.py` - ใช้ `move.quantity` แทน `move.quantity_done`
2. `wizards/mrp_stock_request_allocate_wizard.py` - ใช้ `move_line.quantity` แทน `qty_done`

## สรุป

✅ แก้ไข field name จาก `qty_done` → `quantity`  
✅ รองรับ Odoo 17 architecture  
✅ Allocation wizard ทำงานได้สมบูรณ์  
✅ บันทึก consumed quantity ถูกต้อง  

---

*แก้ไขเมื่อ: 10/10/2025*  
*Issue: Invalid field 'qty_done' on stock.move.line*  
*Status: ✅ Fixed*
