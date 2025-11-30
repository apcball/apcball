# สรุป: Cross-Warehouse Return (คืนสินค้าข้ามคลัง)
## Version 17.0.1.1.6

## ความสามารถใหม่

### เคสการใช้งาน
**ปัญหาเดิม**: ขายจาก WH-A แต่ลูกค้าคืนของเข้าคลัง WH-B → ระบบไม่อนุญาต

**การแก้ไข v17.0.1.1.6**: รองรับการคืนข้าม Warehouse แบบปลอดภัย

### ตัวอย่างการใช้งาน

```
สถานการณ์:
1. รับสินค้า 10 ชิ้น เข้าคลังกรุงเทพ @ 100 บาท/ชิ้น
2. ขายสินค้า 10 ชิ้น จากคลังกรุงเทพ
3. ลูกค้าคืนสินค้า 10 ชิ้น ที่คลังเชียงใหม่ (คนละคลัง!)

ผลลัพธ์:
✅ ระบบคำนวณต้นทุนจาก คลังกรุงเทพ (100 บาท/ชิ้น)
✅ สร้าง Layer ที่คลังเชียงใหม่ (ที่ของกลับเข้ามา)
✅ คลังเชียงใหม่มีสต็อก 10 ชิ้น @ 100 บาท พร้อมขายต่อ
```

## หลักการทำงาน

### 1. การกำหนดต้นทุน (Cost Determination)

```
ต้นทุนมาจาก: คลังต้นทาง (ที่ขายออก)
├─ ใช้ FIFO cost จากการขายครั้งแรก
├─ รวม landed cost ด้วย (ถ้ามี)
└─ ไม่คำนวณใหม่ ไม่เฉลี่ย

Layer อยู่ที่: คลังปลายทาง (ที่ของกลับเข้า)
├─ สต็อกอยู่คลังที่รับของจริง
├─ สามารถขายต่อจากคลังนี้ได้
└─ เข้า FIFO queue ของคลังนี้
```

### 2. การไหลของต้นทุน (Cost Flow)

**ก่อน Return:**
- คลัง A: มีสต็อก 10 ชิ้น @ 100 บาท
- คลัง B: ไม่มีสต็อก

**ขาย 10 ชิ้นจากคลัง A:**
- คลัง A: สต็อก 0 ชิ้น (ขายไป 10 @ 100 บาท)
- คลัง B: ไม่มีสต็อก

**Return 10 ชิ้นเข้าคลัง B:**
- คลัง A: สต็อก 0 ชิ้น (ยังเป็น 0)
- คลัง B: สต็อก 10 ชิ้น @ 100 บาท (cost จาก A)

**ขาย 5 ชิ้นจากคลัง B:**
- คลัง A: สต็อก 0 ชิ้น
- คลัง B: สต็อก 5 ชิ้น @ 100 บาท (ใช้ FIFO จากของที่คืนมา)

### 3. ข้อดี

#### ด้านธุรกิจ
- ✅ ลูกค้าคืนของที่คลังใกล้ที่สุด ลดค่าขนส่ง
- ✅ เพิ่มความพึงพอใจของลูกค้า
- ✅ บริหารสต็อกยืดหยุ่นขึ้น

#### ด้านบัญชี
- ✅ ต้นทุนแม่นยำ ไม่ต้องเดา
- ✅ ใช้ต้นทุนจากธุรกรรมเดิม
- ✅ มี audit trail ชัดเจน

#### ด้านสต็อก
- ✅ สต็อกแสดงในคลังที่ถูกต้อง
- ✅ ไม่มีสต็อกติดลบ
- ✅ FIFO แต่ละคลังเป็นอิสระ

## การใช้งาน

### ขั้นตอนทั่วไป

1. **สร้าง Return Picking**
   - เลือก Picking Type: Receipts ของคลังปลายทาง
   - Location: Customer/Supplier → คลังปลายทาง

2. **เชื่อมโยงกับ Original Move**
   ```python
   return_move.origin_returned_move_id = original_delivery_move.id
   ```
   หรือใช้ Return Wizard ของ Odoo (แนะนำ)

3. **Validate Return**
   - ระบบจะคำนวณต้นทุนอัตโนมัติ
   - สร้าง Layer ที่คลังปลายทาง
   - พร้อมใช้งานทันที

### ตัวอย่าง Python Code

```python
# Step 1: Create return picking
return_picking = self.env['stock.picking'].create({
    'picking_type_id': warehouse_b.in_type_id.id,
    'location_id': customer_location.id,
    'location_dest_id': warehouse_b.lot_stock_id.id,
})

# Step 2: Create return move linked to original
return_move = self.env['stock.move'].create({
    'name': 'Return to WH-B',
    'product_id': product.id,
    'product_uom_qty': 10.0,
    'product_uom': product.uom_id.id,
    'picking_id': return_picking.id,
    'location_id': customer_location.id,
    'location_dest_id': warehouse_b.lot_stock_id.id,
    'origin_returned_move_id': original_delivery_move.id,  # สำคัญ!
})

# Step 3: Validate
return_picking.action_confirm()
return_picking.action_assign()
return_picking.button_validate()

# ผลลัพธ์: Layer ถูกสร้างที่ WH-B ด้วยต้นทุนจาก WH-A
```

## การทดสอบ

### รัน Test Suite

```bash
# รัน test ทั้งหมด
cd /opt/instance1/odoo17
./odoo-bin -c /etc/odoo.conf -d your_database \
  --test-enable \
  --test-tags=stock_fifo_by_location \
  --log-level=test

# รัน test เฉพาะ cross-warehouse return
./odoo-bin -c /etc/odoo.conf -d your_database \
  --test-enable \
  --test-tags=stock_fifo_by_location.test_cross_warehouse_return \
  --log-level=test
```

### Test Cases

1. ✅ **Basic Cross-Warehouse Return**
   - Return พื้นฐานข้ามคลัง
   - ตรวจสอบต้นทุนและ warehouse ถูกต้อง

2. ✅ **Sell from New Warehouse**
   - Return เข้าคลัง B แล้วขายจากคลัง B
   - ตรวจสอบ FIFO ทำงานที่คลังใหม่

3. ✅ **Cost Determinism**
   - หลาย receipt ต่างราคา
   - Return ใช้ต้นทุน FIFO เดิม ไม่เฉลี่ย

4. ✅ **No Negative Balance**
   - ตรวจสอบไม่มี remaining_qty ติดลบ

## แก้ปัญหา

### ปัญหา: ต้นทุน Return ผิด

**ตรวจสอบ**:
```python
# 1. เช็ค link ถูกต้อง
print(return_move.origin_returned_move_id)  # ต้องไม่เป็น False

# 2. เช็ค original layer มี
original_layers = self.env['stock.valuation.layer'].search([
    ('stock_move_id', '=', original_move.id),
    ('quantity', '<', 0),
])
print(original_layers)  # ต้องมี record

# 3. เช็ค unit_cost
print(original_layers[0].unit_cost)  # ต้องมีค่า
```

### ปัญหา: Layer สร้างผิดคลัง

**ตรวจสอบ**:
```python
# 1. เช็ค destination location
print(return_move.location_dest_id.warehouse_id)

# 2. เช็ค layer ที่สร้าง
return_layers = self.env['stock.valuation.layer'].search([
    ('stock_move_id', '=', return_move.id),
])
for layer in return_layers:
    print(f"Layer {layer.id}: warehouse={layer.warehouse_id.name}")
```

## สรุป

### วิธีการที่ใช้ (Implementation)

```
✅ ตอน Return อิงจาก: Original out move (การขายเดิม)
✅ ต้นทุนมาจาก: Layer ที่ใช้ตอนขาย (จาก WH-A)
✅ สร้าง Layer ที่: คลังปลายทาง (WH-B)
✅ Cost Flow: Deterministic (แน่นอน ไม่งง)
✅ FIFO Scope: แต่ละคลังเป็นอิสระ
```

### ผลลัพธ์

```
เมื่อก่อน: ❌ Return ข้ามคลังไม่ได้ (Validation Error)
ตอนนี้:   ✅ Return ข้ามคลังได้ แม่นยำ ปลอดภัย
```

### Files ที่แก้ไข

1. **`models/stock_move.py`**
   - `_get_fifo_valuation_layer_warehouse()`: รองรับ cross-warehouse return
   - `_action_done()`: ลบ validation ที่บล็อก
   - `_update_created_layers_warehouse()`: จัดการ cost และ warehouse

2. **`tests/test_cross_warehouse_return.py`** (ใหม่)
   - Test suite ครบถ้วน 4 scenarios

3. **`tests/__init__.py`**
   - เพิ่ม import test ใหม่

4. **`__manifest__.py`**
   - Version: 17.0.1.1.5 → 17.0.1.1.6
   - เพิ่ม description feature ใหม่

## เอกสารเพิ่มเติม

- **English Guide**: `CROSS_WAREHOUSE_RETURN_IMPLEMENTATION_GUIDE.md`
- **Test File**: `tests/test_cross_warehouse_return.py`
- **Manifest**: `__manifest__.py`

## ติดต่อ

- Author: APC Ball
- Version: 17.0.1.1.6
- Date: 30 พฤศจิกายน 2568

---

**หมายเหตุ**: Feature นี้ออกแบบให้ปลอดภัยและแม่นยำ ไม่กระทบ FIFO logic เดิม แค่เพิ่มความยืดหยุ่นในการบริหารสต็อกข้ามคลัง
