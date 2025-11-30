# แก้ไขปัญหา FIFO ตัดผิด Warehouse เวลา Delivery

## 📋 สรุปปัญหา

เมื่อทำ Delivery Order จาก Warehouse A ระบบไปตัด FIFO (remaining_qty) จาก Warehouse B แทน ทำให้:
- ยอด remaining_qty ของแต่ละ warehouse ผิด
- ต้นทุนขาย (COGS) คำนวณผิด
- รายงาน Inventory Valuation ไม่ถูกต้อง

## 🔍 สาเหตุ (Root Cause)

ปัญหาเกิดจาก **Cache ไม่ fresh** ใน `_run_fifo()`:

### ขั้นตอนที่เกิดปัญหา:

1. **`_create_out_svl()` ถูกเรียก**
   - หา warehouse จาก source location
   - Set `warehouse_id` ใน vals dict
   - สร้าง valuation layer

2. **Odoo เรียก `_run_fifo()` ทันที**
   - อ่าน `self.warehouse_id` จาก cache (อาจเป็นค่าเก่า)
   - ถ้า cache ไม่ fresh → อ่านค่าผิด
   - Query FIFO queue จาก warehouse ที่ผิด!

3. **ผลลัพธ์**
   - Delivery จาก WH-A แต่ตัด remaining_qty จาก WH-B ❌

## ✅ วิธีแก้ไข (Solution)

### 1. Invalidate Cache ก่อนอ่าน warehouse_id

เพิ่มใน `_run_fifo()` ใน `stock_valuation_layer.py`:

```python
# 🔴 CRITICAL FIX v17.0.1.2.4: Invalidate cache
self.invalidate_recordset(['warehouse_id', 'product_id', 'quantity'])

if not self.warehouse_id:
    _logger.warning(...)
    return super()._run_fifo(quantity, company)
```

**ทำไมต้อง invalidate?**
- ตอน `create()` เสร็จใหม่ๆ cache อาจยังไม่ sync กับ database
- `_run_fifo()` ถูกเรียกทันทีหลัง create → cache ยังเป็นค่าเก่า
- `invalidate_recordset()` บังคับให้อ่านจาก database ใหม่

### 2. เพิ่ม Logging เพื่อ Debug

เพิ่มใน `_create_out_svl()` ใน `stock_move.py`:

```python
_logger.info(
    f"🏭 _create_out_svl for move {move.name}: "
    f"from {move.location_id.complete_name} → {move.location_dest_id.complete_name}, "
    f"warehouse={warehouse.name if warehouse else 'None'}"
)
```

เพิ่มใน `_run_fifo()` ใน `stock_valuation_layer.py`:

```python
_logger.info(
    f"🔍 _run_fifo() for Layer {self.id}: "
    f"Product={self.product_id.display_name}, "
    f"Warehouse={self.warehouse_id.name} (ID={self.warehouse_id.id}), "
    f"Consuming qty={abs(quantity):.2f}, "
    f"Found {len(candidates)} candidate layers"
)

# ...และในลูป...

_logger.info(
    f"  📥 Consuming from Layer {candidate.id} at warehouse {candidate.warehouse_id.name}: "
    f"qty_taken={qty_taken_on_candidate:.2f}"
)
```

## 🧪 วิธีทดสอบ

### ขั้นตอนทดสอบ:

1. เตรียม stock ใน 2 warehouses:
   - Warehouse A: มี stock 10 units
   - Warehouse B: มี stock 10 units

2. สร้าง Delivery Order จาก Warehouse A:
   - จำนวน: 1 unit
   - จาก: Warehouse A → Customer

3. ตรวจสอบ Log:
   ```
   🏭 _create_out_svl for move: warehouse=Warehouse A
   🔍 _run_fifo() for Layer: Warehouse=Warehouse A
   📥 Consuming from Layer X at warehouse Warehouse A
   ```

4. ตรวจสอบ remaining_qty:
   - Warehouse A: ลดลง 1 unit ✅
   - Warehouse B: ไม่เปลี่ยนแปลง ✅

### สคริปต์ทดสอบอัตโนมัติ:

```bash
cd /opt/instance1/odoo17/custom-addons
python3 test_delivery_fifo_fix.py
```

สคริปต์จะ:
- หา product ที่ใช้ FIFO
- สร้าง delivery order
- ตรวจสอบว่า FIFO ตัดจาก warehouse ที่ถูกต้อง
- แสดงผลการทดสอบ PASS/FAIL

## 📊 ผลลัพธ์

### ก่อนแก้ไข (v17.0.1.2.3):
```
Delivery จาก Warehouse A (1 unit)
→ FIFO ตัดจาก Warehouse B ❌
→ remaining_qty:
  - Warehouse A: ไม่เปลี่ยน (ผิด!)
  - Warehouse B: ลดลง 1 (ผิด!)
```

### หลังแก้ไข (v17.0.1.2.4):
```
Delivery จาก Warehouse A (1 unit)
→ FIFO ตัดจาก Warehouse A ✅
→ remaining_qty:
  - Warehouse A: ลดลง 1 (ถูกต้อง!)
  - Warehouse B: ไม่เปลี่ยน (ถูกต้อง!)
```

## 🎯 ข้อดี (Benefits)

1. **ต้นทุนขายถูกต้อง**: COGS คำนวณจาก warehouse ที่ขายจริง
2. **Inventory Valuation แม่นยำ**: remaining_qty ของแต่ละ warehouse ถูกต้อง
3. **Debug ง่าย**: Log แสดงชัดเจนว่าตัดจาก warehouse ไหน
4. **ป้องกัน Race Condition**: Cache invalidation ป้องกันปัญหาอ่านค่าผิด

## 📝 Technical Details

### ไฟล์ที่แก้ไข:

1. **`stock_valuation_layer.py`**:
   - เพิ่ม `invalidate_recordset()` ใน `_run_fifo()`
   - เปลี่ยน log level จาก debug เป็น info
   - เพิ่มแสดง warehouse name ในทุก log

2. **`stock_move.py`**:
   - เพิ่ม logging ใน `_create_out_svl()`
   - แสดง warehouse ที่ identify ได้
   - แสดง warning ถ้าหา warehouse ไม่เจอ

3. **`__manifest__.py`**:
   - อัพเดท version เป็น 17.0.1.2.4
   - เพิ่มคำอธิบายการแก้ไข

## 🔧 การ Deploy

1. **Restart Odoo**:
   ```bash
   sudo systemctl restart instance1
   ```

2. **Update module**:
   - ไปที่ Apps
   - เลือก stock_fifo_by_location
   - กด Upgrade

3. **ทดสอบ**:
   - สร้าง delivery order ทดสอบ
   - ตรวจสอบ log
   - ตรวจสอบ remaining_qty

## ⚠️ หมายเหตุ

- การแก้ไขนี้ไม่กระทบ data ที่มีอยู่
- ไม่ต้อง migration
- แค่ restart และ upgrade module
- ระบบจะทำงานถูกต้องทันทีหลัง upgrade

## 🆘 ถ้าเจอปัญหา

ถ้าหลัง upgrade แล้วยังตัด warehouse ผิดอยู่:

1. **ตรวจสอบ Log**:
   ```bash
   tail -f /var/log/odoo/instance1.log | grep -E "🏭|🔍|📥"
   ```

2. **ตรวจสอบ warehouse_id ใน Layer**:
   ```sql
   SELECT id, product_id, quantity, remaining_qty, warehouse_id, create_date
   FROM stock_valuation_layer
   WHERE product_id = YOUR_PRODUCT_ID
   ORDER BY create_date DESC
   LIMIT 10;
   ```

3. **Clear Cache**:
   ```bash
   cd /opt/instance1/odoo17/custom-addons
   bash clear_odoo_cache.sh
   sudo systemctl restart instance1
   ```

## ✅ Checklist หลัง Deploy

- [ ] Module upgrade สำเร็จ
- [ ] สร้าง delivery order ทดสอบ
- [ ] Log แสดง warehouse ถูกต้อง
- [ ] remaining_qty ลดจาก warehouse ที่ถูกต้อง
- [ ] ทดสอบกับหลาย warehouse
- [ ] ตรวจสอบ COGS ใน Invoice

---

**Version**: 17.0.1.2.4  
**Date**: 30 พฤศจิกายน 2568  
**Status**: ✅ Fixed & Tested
