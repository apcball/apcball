# สรุป: Scripts สำหรับจัดการ Valuation by Warehouse

## 📦 ไฟล์ที่สร้างขึ้น

```
stock_fifo_by_location/scripts/
├── fix_valuation_by_warehouse.py          # แก้ไขข้อมูล valuation ที่ผิด
├── create_initial_stock_by_warehouse.py   # สร้าง stock เริ่มต้นแยกคลัง
├── quick_fix_mog_test.sh                  # Script รวมใช้งานง่าย
├── initial_stock_template.csv             # Template สำหรับยกของเข้า
├── README.md                              # คู่มือฉบับเต็ม
└── QUICKSTART.md                          # เริ่มต้นใช้งานเร็ว
```

---

## 🎯 ปัญหาที่แก้ได้

### ปัญหา 1: Remaining Qty ≠ Moved Qty
**สาเหตุ**: Valuation layer ไม่ได้แยกตาม warehouse ชัดเจน

**วิธีแก้**:
```bash
./quick_fix_mog_test.sh
# เลือก: 1. แก้ไขข้อมูล valuation
```

**ผลลัพธ์**:
- ✅ warehouse_id ถูกกำหนดให้ทุก layer
- ✅ remaining_qty คำนวณใหม่แยกตาม warehouse
- ✅ FIFO ทำงานถูกต้องในแต่ละคลัง

### ปัญหา 2: ต้องการยกของเข้าคลังใหม่
**สาเหตุ**: เริ่มใช้งานระบบ หรือปรับปรุงยอด

**วิธีแก้**:
```bash
./quick_fix_mog_test.sh
# เลือก: 2. ยกของเข้าคลัง
```

**หรือใช้ CSV**:
1. แก้ไข `initial_stock_template.csv`
2. รันใน Odoo shell (ดูตัวอย่างใน README.md)

**ผลลัพธ์**:
- ✅ สร้าง stock.move (Inventory Adjustment)
- ✅ สร้าง stock.valuation.layer พร้อม warehouse_id
- ✅ remaining_qty = quantity (ยังไม่มีการใช้)

---

## 🚀 วิธีใช้งานแบบเร็ว

### ขั้นตอน 1: Backup ข้อมูล
```bash
pg_dump -U postgres -d MOG_TEST > /backup/MOG_TEST_$(date +%Y%m%d).sql
```

### ขั้นตอน 2: รัน Script
```bash
cd /opt/instance1/odoo17/custom-addons/stock_fifo_by_location/scripts
./quick_fix_mog_test.sh
```

### ขั้นตอน 3: ตรวจสอบผล
- เปิด Odoo UI → Inventory → Reporting → **Stock Valuation**
- Group By: **Warehouse > Product**
- ตรวจสอบ: **Moved Qty = Remaining Qty** ✅

---

## 📊 ตัวอย่างผลลัพธ์

### ก่อนแก้ไข:
```
Product: PROD001
  ├─ All Warehouses: Moved=150, Remaining=120  ❌ ผิด!
  ├─ Dead Stock: Moved=100, Remaining=80      ❌ 
  └─ SCG: Moved=50, Remaining=40              ❌
```

### หลังแก้ไข:
```
Product: PROD001
  ├─ Dead Stock: Moved=100, Remaining=100  ✅ ถูกต้อง!
  └─ SCG: Moved=50, Remaining=50           ✅ ถูกต้อง!
```

---

## ⚙️ Technical Details

### Script 1: fix_valuation_by_warehouse.py

**การทำงาน**:
1. หา layers ที่ไม่มี warehouse_id → กำหนดจาก location
2. คำนวณ FIFO แยกตาม warehouse
3. อัปเดต remaining_qty และ remaining_value

**Algorithm**:
```python
for warehouse in warehouses:
    for product in products:
        layers = get_layers(product, warehouse, order_by='date')
        
        fifo_queue = []
        for layer in layers:
            if layer.quantity > 0:
                # เพิ่มเข้า queue
                fifo_queue.append(layer)
            else:
                # ตัดจาก queue (FIFO)
                consume_from_queue(fifo_queue, abs(layer.quantity))
```

### Script 2: create_initial_stock_by_warehouse.py

**การทำงาน**:
1. สร้าง stock.move (Inventory → Stock Location)
2. สร้าง stock.valuation.layer พร้อม:
   - warehouse_id
   - quantity (บวก)
   - unit_cost
   - remaining_qty = quantity
   - remaining_value = quantity × unit_cost

---

## 🔧 Troubleshooting

### ปัญหา: Script รันไม่ได้
```bash
# ตรวจสอบ Python path
which python3

# ตรวจสอบ Odoo path
ls -la /opt/instance1/odoo17/odoo-bin

# ตรวจสอบ permissions
chmod +x quick_fix_mog_test.sh
```

### ปัญหา: ข้อมูลยังไม่ถูก
```python
# ตรวจสอบ warehouse_id
layers = env['stock.valuation.layer'].search([
    ('warehouse_id', '=', False)
])
print(f"Layers ที่ไม่มี warehouse: {len(layers)}")

# ตรวจสอบ FIFO queue
for wh in env['stock.warehouse'].search([]):
    layers = env['stock.valuation.layer'].search([
        ('product_id', '=', product.id),
        ('warehouse_id', '=', wh.id)
    ], order='create_date')
    
    print(f"\n{wh.name}:")
    for layer in layers:
        print(f"  {layer.quantity:>8.2f} | {layer.remaining_qty:>8.2f}")
```

---

## 📚 เอกสารเพิ่มเติม

- 📖 คู่มือฉบับเต็ม: `scripts/README.md`
- 🚀 เริ่มต้นใช้งาน: `scripts/QUICKSTART.md`
- 📝 Template CSV: `scripts/initial_stock_template.csv`

---

## ✅ Checklist หลังใช้งาน

- [ ] Backup database เรียบร้อย
- [ ] รัน script ด้วย dry_run=True ก่อน
- [ ] ตรวจสอบผลลัพธ์ใน UI
- [ ] Moved Qty = Remaining Qty ทุกคลัง
- [ ] ทดสอบรับ-จ่ายสินค้า
- [ ] Restart Odoo instance
- [ ] บันทึก log ไว้อ้างอิง

---

**เวอร์ชัน**: 17.0.1.1.3  
**วันที่**: 2025-11-28  
**ผู้พัฒนา**: APC Ball

---

## 🎉 สรุป

Scripts เหล่านี้จะช่วย:
1. ✅ แก้ไข valuation layer ให้ถูกต้องตาม warehouse
2. ✅ คำนวณ remaining qty/value ใหม่แยกตาม warehouse
3. ✅ ยกของเข้าคลังได้อย่างถูกต้อง
4. ✅ ทำให้ FIFO ทำงานถูกต้องในแต่ละคลัง

**ผลลัพธ์**: Moved Qty = Remaining Qty ในทุก warehouse ✅
