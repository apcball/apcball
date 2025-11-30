# Stock FIFO by Location - Version 17.0.1.1.5
# Critical Fix: Inter-Warehouse Transfer Layer Creation

## วันที่: 30 พฤศจิกายน 2568

## ปัญหาที่แก้ไข

### ปัญหาหลัก: คลังปลายทางมี stock แต่ไม่มี valuation layer

เมื่อทำ Inter-warehouse transfer จาก WH-A → WH-B:
- ✅ Odoo สร้าง **negative layer** ที่ WH-A (เบิกออก)
- ❌ Odoo **ไม่สร้าง positive layer** ที่ WH-B (รับเข้า)
- ผลลัพธ์: ที่ WH-B มี stock quantity แต่ `remaining_qty = 0`
- เมื่อขายจาก WH-B: ระบบหา layer ไม่เจอ → หยิบ layer จาก warehouse อื่น → คำนวณต้นทุนผิด

## แนวคิดที่ถูกต้อง

### เวลา Transfer ข้ามคลัง A → B:

#### 1. คลังต้นทาง (WH-A) - ทำเหมือน "เบิกออก"
- หา FIFO layer ของ WH-A ตาม quantity ที่ย้าย
- `remaining_qty` ลดลง (ผ่าน `_run_fifo()`)
- สร้าง SVL out:
  ```python
  {
      'quantity': -qty,
      'value': -cost_total,  # from FIFO
      'warehouse_id': WH-A.id,
      'remaining_qty': 0.0,
      'remaining_value': 0.0,
  }
  ```

#### 2. คลังปลายทาง (WH-B) - ต้องมี "in layer ใหม่" เสมอ
- สร้าง SVL in:
  ```python
  {
      'quantity': +qty,
      'value': +cost_total,  # เดิมจาก WH-A
      'unit_cost': cost_total / qty,
      'warehouse_id': WH-B.id,
      'remaining_qty': qty,  # ✅ CRITICAL: นี่คือแหล่ง FIFO ของ WH-B
      'remaining_value': cost_total,
  }
  ```
- Layer นี้คือ **แหล่ง FIFO** ของ WH-B สำหรับการขาย/เบิกครั้งต่อไป

### ⚠️ ถ้าข้อ 2 ไม่ทำ
- ที่คลัง B จะมี stock ปริมาณ แต่ไม่มี valuation layer
- `remaining_qty = 0` ตลอด
- พอขายจาก WH-B ระบบจะหา layer ไม่เจอ
- ไปหยิบ global layer / หรือ warehouse อื่น / หรือคำนวณผิด

## การแก้ไข

### 1. ปรับปรุง `_ensure_inter_warehouse_valuation_layers()`

**ไฟล์**: `models/stock_move.py`

**การเปลี่ยนแปลง**:
```python
def _ensure_inter_warehouse_valuation_layers(self):
    """
    🔴 CRITICAL: Ensure BOTH negative (source) AND positive (dest) 
    valuation layers exist for inter-warehouse transfers.
    """
    # ตรวจสอบว่ามี layer อยู่แล้วหรือไม่
    has_negative_source = any(
        l.quantity < 0 and l.warehouse_id.id == source_wh.id 
        for l in existing_layers
    )
    has_positive_dest = any(
        l.quantity > 0 and l.warehouse_id.id == dest_wh.id 
        for l in existing_layers
    )
    
    # สร้าง negative layer (ถ้ายังไม่มี)
    if not has_negative_source:
        neg_layer = Layer.create({
            'warehouse_id': source_wh.id,
            'quantity': -qty,
            'value': -cost_total,
            'remaining_qty': 0.0,
        })
        # 🔴 CRITICAL: Run FIFO to consume
        neg_layer._run_fifo(-qty, company)
    
    # 🔴 CRITICAL: สร้าง positive layer (ถ้ายังไม่มี)
    if not has_positive_dest:
        pos_layer = Layer.create({
            'warehouse_id': dest_wh.id,
            'quantity': qty,
            'value': cost_total,
            'remaining_qty': qty,  # ✅ FIFO source
            'remaining_value': cost_total,
        })
```

**จุดสำคัญ**:
1. ✅ ตรวจสอบว่า layer แต่ละตัวมีอยู่แล้วหรือไม่ (ป้องกันสร้างซ้ำ)
2. ✅ สร้าง **negative layer** ที่ source warehouse
3. ✅ เรียก `_run_fifo()` เพื่อตัด stock จาก FIFO queue ของ source
4. ✅ สร้าง **positive layer** ที่ destination warehouse
5. ✅ Set `remaining_qty = qty` เพื่อให้เป็น FIFO source สำหรับการขาย/เบิกครั้งต่อไป

### 2. เพิ่ม Logging ใน `_run_fifo()`

**ไฟล์**: `models/stock_valuation_layer.py`

**การเปลี่ยนแปลง**:
```python
def _run_fifo(self, quantity, company):
    """Run FIFO per warehouse with detailed logging"""
    
    # Log การค้นหา candidates
    _logger.info(
        f"🔍 _run_fifo() for Layer {self.id}: "
        f"Product={product.name}, "
        f"Warehouse={warehouse.name}, "
        f"Consuming qty={abs(quantity):.2f}, "
        f"Found {len(candidates)} candidate layers"
    )
    
    # Log การ consume แต่ละ layer
    for candidate in candidates:
        _logger.info(
            f"  📥 Consuming from Layer {candidate.id}: "
            f"qty_taken={qty_taken:.2f} @ {unit_cost:.4f}/unit, "
            f"remaining: {before:.2f} → {after:.2f}"
        )
    
    # Log ผลลัพธ์สุดท้าย
    _logger.info(
        f"✅ _run_fifo() complete: "
        f"Total value consumed: {tmp_value:.4f}"
    )
```

**ประโยชน์**:
- ตรวจสอบได้ว่า FIFO consume จาก warehouse ไหน
- Debug ได้ง่ายเมื่อมีปัญหา
- เห็นขั้นตอนการ consume แต่ละ layer ชัดเจน

### 3. เพิ่ม Logging ใน `_ensure_inter_warehouse_valuation_layers()`

**ไฟล์**: `models/stock_move.py`

**การเปลี่ยนแปลง**:
```python
_logger.info(
    f"📦 Inter-warehouse move {move.name}: "
    f"{source_wh.name} → {dest_wh.name}, "
    f"Product: {product.name}, Qty: {qty}, "
    f"Existing layers: {len(existing_layers)}, "
    f"Has negative@source: {has_negative_source}, "
    f"Has positive@dest: {has_positive_dest}"
)

_logger.info(f"💰 FIFO cost from {source_wh.name}: unit={unit_cost:.4f}")
_logger.info(f"✅ Created NEGATIVE layer at {source_wh.name}")
_logger.info(f"✅ Ran FIFO consumption at {source_wh.name}")
_logger.info(f"✅ Created POSITIVE layer at {dest_wh.name}")
```

### 4. สร้าง Test Script

**ไฟล์**: `tests/test_inter_warehouse_transfer.py`

**ฟังก์ชัน**:
```python
def test_inter_warehouse_transfer(env):
    """
    Test scenario:
    1. Receive 10 units to WH-A @ 100/unit
    2. Transfer 5 units from WH-A to WH-B
    3. Verify layers created correctly
    4. Sell 3 units from WH-B
    5. Verify FIFO consumption at WH-B
    """
```

**วิธีใช้**:
```bash
odoo-bin shell -d <database> -c <config>
>>> execfile('/opt/instance1/odoo17/custom-addons/stock_fifo_by_location/tests/test_inter_warehouse_transfer.py')
>>> test_inter_warehouse_transfer(env)
```

## สรุปการแก้ไข

### ไฟล์ที่แก้ไข

1. **`models/stock_move.py`**
   - ✅ ปรับ `_ensure_inter_warehouse_valuation_layers()` ให้สร้าง layer ทั้งสองแน่นอน
   - ✅ เพิ่ม logging ละเอียด
   - ✅ ตรวจสอบว่า layer มีอยู่แล้วหรือไม่ก่อนสร้าง

2. **`models/stock_valuation_layer.py`**
   - ✅ เพิ่ม logging ใน `_run_fifo()` เพื่อ debug
   - ✅ แสดงรายละเอียดการ consume แต่ละ layer

3. **`tests/test_inter_warehouse_transfer.py`** (ใหม่)
   - ✅ สร้าง test script ครบวงจร
   - ✅ ทดสอบ receipt → transfer → sale
   - ✅ Verify layer creation ที่ทั้งสอง warehouse

4. **`__manifest__.py`**
   - ✅ อัพเดท version เป็น 17.0.1.1.5
   - ✅ เพิ่ม description ของการแก้ไข

## ผลลัพธ์ที่คาดหวัง

### ก่อนแก้ไข ❌
```
WH-A → WH-B transfer 5 units:
  WH-A: 1 negative layer (qty=-5)
  WH-B: 0 layers ← ❌ ปัญหา!
  
Sale 3 from WH-B:
  ❌ หา layer ไม่เจอ → หยิบจาก WH-A → ผิด!
```

### หลังแก้ไข ✅
```
WH-A → WH-B transfer 5 units:
  WH-A: 1 negative layer (qty=-5, remaining_qty=0)
  WH-B: 1 positive layer (qty=+5, remaining_qty=5) ← ✅ สร้างแล้ว!
  
Sale 3 from WH-B:
  ✅ หา layer ที่ WH-B เจอ → consume 3 → remaining_qty=2
  ✅ ต้นทุนถูกต้องตาม FIFO ของ WH-B
```

## การทดสอบ

### 1. Upgrade Module
```bash
odoo-bin -u stock_fifo_by_location -d <database> -c <config> --stop-after-init
```

### 2. Restart Odoo
```bash
sudo systemctl restart instance1
```

### 3. Run Test Script
```python
odoo-bin shell -d <database> -c <config>
>>> execfile('test_inter_warehouse_transfer.py')
>>> test_inter_warehouse_transfer(env)
```

### 4. Check Logs
```bash
# ดู log file สำหรับ detailed logging
tail -f /var/log/odoo/instance1.log | grep -E '(📦|💰|✅|🔍|📥)'
```

## สิ่งที่ต้องระวัง

1. **Module Upgrade**: ต้อง upgrade module ทุกครั้งหลังแก้ไข
2. **Cache**: Clear cache ด้วย `./clear_odoo_cache.sh` หากจำเป็น
3. **Existing Data**: การแก้ไขนี้จะทำงานกับ transaction ใหม่เท่านั้น สำหรับ layer เก่าอาจต้องรัน migration script

## ข้อดีของการแก้ไขนี้

1. ✅ **ครบถ้วน**: สร้าง layer ทั้งสองเสมอ (negative + positive)
2. ✅ **ป้องกันซ้ำ**: ตรวจสอบว่ามี layer อยู่แล้วก่อนสร้าง
3. ✅ **FIFO ถูกต้อง**: positive layer ที่ destination เป็น FIFO source
4. ✅ **Debug ง่าย**: Logging ละเอียดทุกขั้นตอน
5. ✅ **Testable**: มี test script ทดสอบได้ทันที
6. ✅ **ไม่กระทบเดิม**: ไม่แก้ไข standard Odoo behavior

## สรุป

การแก้ไขนี้แก้ปัญหาสำคัญที่ทำให้ inter-warehouse transfer ใน module `stock_fifo_by_location` ทำงานได้ถูกต้องตามหลัก FIFO per warehouse โดย:

1. **สร้าง negative layer** ที่ source warehouse (ตัด stock จาก FIFO queue)
2. **สร้าง positive layer** ที่ destination warehouse (เป็น FIFO source ใหม่)
3. **Logging ละเอียด** เพื่อ debug และ monitor
4. **Test script** เพื่อ verify การทำงาน

✅ **ผลลัพธ์**: ขายจาก destination warehouse หลังจาก transfer แล้วใช้ FIFO cost ถูกต้อง ไม่ไปหยิบ layer จาก warehouse อื่น!
