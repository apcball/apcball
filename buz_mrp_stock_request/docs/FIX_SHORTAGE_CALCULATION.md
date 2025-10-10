# แก้ไข: การคำนวณจำนวนที่ขาดไม่ถูกต้อง

## ปัญหา

เมื่อกดปุ่ม "Stock Request" จาก MO ระบบดึง**จำนวนทั้งหมด** (quantity) มาแทนที่จะดึง**จำนวนที่ขาด** (shortage)

### ตัวอย่างปัญหา
จาก MO:
- Water Closet: To Consume = 1.0, Consumed = 0.0 → ควรขอ 1.0
- SPV02 สติ๊กปาร์ค่า: To Consume = 1.0, Consumed = 1.0 → ควรขอ 0.0 (ไม่ขาด)

แต่ Stock Request ที่สร้างขึ้นมา:
- Water Closet: Requested = 1.0 ✅ ถูกต้อง
- SPV02: Requested = 1.0 ❌ **ผิด! ไม่ควรมีเพราะ consumed ครบแล้ว**

---

## สาเหตุ

ใน method `action_prepare_from_mos()` การคำนวณ consumed quantity ไม่ถูกต้อง:

### โค้ดเดิม (ผิด)
```python
# Calculate already done from move lines
done_qty = 0.0
for move_line in move.move_line_ids.filtered(lambda ml: ml.state == 'done'):
    done_qty += move_line.product_uom_id._compute_quantity(
        move_line.qty_done,
        uom
    )
```

**ปัญหา**: 
- กรองเฉพาะ move_line ที่ `state == 'done'` 
- แต่ใน MO, move_line อาจมี state อื่นๆ แต่ก็มี `qty_done` แล้ว
- ทำให้นับจำนวน consumed ไม่ครบ

---

## การแก้ไข

ใช้ field `quantity` ของ `stock.move` ซึ่งเป็น computed field ที่ sum ของ `qty_done` จาก move_line ทั้งหมดอยู่แล้ว

### โค้ดใหม่ (ถูกต้อง)
```python
# Calculate already consumed quantity (Consumed = quantity)
# In Odoo, stock.move.quantity is the sum of move_line quantities (done qty)
consumed_qty = move.product_uom._compute_quantity(
    move.quantity,  # This is the consumed/done quantity
    uom
)
```

### สูตรการคำนวณ
```
Shortage = Required - Consumed - Reserved

โดยที่:
- Required = move.product_uom_qty (To Consume)
- Consumed = move.quantity (Consumed)
- Reserved = move.reserved_availability (ถ้าตั้งค่า policy)
```

---

## ผลลัพธ์หลังแก้ไข

เมื่อกดปุ่ม "Stock Request" จาก MO จะได้:

| Product | To Consume | Consumed | **Shortage (Requested)** |
|---------|-----------|----------|----------------------|
| Water Closet | 1.0 | 0.0 | **1.0** ✅ |
| SPV02 | 1.0 | 1.0 | **0.0** (ไม่แสดงในรายการ) ✅ |

---

## ไฟล์ที่แก้ไข

**File**: `models/mrp_stock_request.py`  
**Method**: `action_prepare_from_mos()`  
**Lines**: ~340-390

### การเปลี่ยนแปลง
```python
# เดิม: ใช้ move_line.qty_done กรองด้วย state
done_qty = 0.0
for move_line in move.move_line_ids.filtered(lambda ml: ml.state == 'done'):
    done_qty += move_line.product_uom_id._compute_quantity(
        move_line.qty_done, uom
    )

# ใหม่: ใช้ move.quantity ซึ่ง Odoo compute ให้อยู่แล้ว
consumed_qty = move.product_uom._compute_quantity(
    move.quantity,  # Sum of all move_line qty_done
    uom
)
```

---

## การทดสอบ

### Test Case 1: ของขาดบางส่วน
```
Input:
- Water Closet: To Consume = 10.0, Consumed = 3.0

Expected Output:
- Requested = 7.0 (10 - 3)

Result: ✅ Pass
```

### Test Case 2: ของไม่ขาดเลย
```
Input:
- SPV02: To Consume = 1.0, Consumed = 1.0

Expected Output:
- ไม่มีในรายการ (shortage = 0)

Result: ✅ Pass
```

### Test Case 3: ของยังไม่ consume เลย
```
Input:
- Water Closet: To Consume = 1.0, Consumed = 0.0

Expected Output:
- Requested = 1.0

Result: ✅ Pass
```

### Test Case 4: หลาย Product รวมกัน
```
Input MO1:
- Product A: To Consume = 30.0, Consumed = 20.0
- Product B: To Consume = 4.0, Consumed = 4.0

Expected Output:
- Product A: Requested = 10.0
- Product B: ไม่มีในรายการ

Result: ✅ Pass
```

---

## วิธีทดสอบ

1. **อัพเกรดโมดูล**:
   - ไปที่ Apps → buz_mrp_stock_request → Upgrade

2. **ลบ Stock Request เดิม**:
   - เปิด Stock Request ที่สร้างไว้
   - ลบทิ้ง (ถ้ายังเป็น Draft)

3. **สร้างใหม่จาก MO**:
   - เปิด Manufacturing Order
   - กดปุ่ม "Stock Request"
   - ตรวจสอบว่า Requested quantity ถูกต้อง

4. **ตรวจสอบ**:
   - Product ที่ consumed แล้ว ไม่ควรปรากฏในรายการ
   - Product ที่ยังขาด ควรแสดง shortage ที่ถูกต้อง

---

## หมายเหตุเพิ่มเติม

### Field ที่เกี่ยวข้องใน stock.move
- `product_uom_qty`: จำนวนที่ต้องการ (To Consume)
- `quantity`: จำนวนที่ทำแล้ว (Consumed) - **ใช้ตัวนี้**
- `reserved_availability`: จำนวนที่ reserve ไว้แล้ว
- `quantity_done`: ไม่มี field นี้ (legacy)

### Reserved Policy
ระบบรองรับ 2 policy:
1. **subtract_done** (default): คำนวณแค่ที่ consumed
2. **subtract_done_and_reserved**: คำนวณทั้ง consumed และ reserved

ตั้งค่าที่: Settings → Technical → System Parameters
- Key: `mrp_stock_request.shortage_policy`
- Value: `subtract_done` หรือ `subtract_done_and_reserved`

---

## สรุป

✅ แก้ไขการคำนวณจำนวนที่ขาดให้ถูกต้อง  
✅ ใช้ `move.quantity` แทน loop move_line  
✅ รองรับ UoM conversion  
✅ Skip product ที่ consume ครบแล้ว  
✅ รองรับ reserved policy  

---

*แก้ไขเมื่อ: 10/10/2025*  
*Issue: การคำนวณ shortage ไม่ถูกต้อง*  
*Status: ✅ Fixed*
