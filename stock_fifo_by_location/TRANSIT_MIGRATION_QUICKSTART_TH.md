# 🚀 Quick Start: Transit Location Migration

## สำหรับผู้ดูแลระบบ (System Administrators)

### การติดตั้งและ Migration แบบเร็ว

```bash
# 1. เข้าสู่ Odoo shell
odoo-bin shell -d your_database

# 2. Import module
from odoo.addons.stock_fifo_by_location.migrations import populate_location_id as m

# 3. วิเคราะห์ Transit Locations
stats = m.analyze_transit_locations(env)

# 4. Migrate Transit Locations
result_transit = m.populate_transit_location_layers(env)
print(f"✅ Transit migrated: {result_transit['successful']}")

# 5. Migrate ส่วนที่เหลือทั้งหมด
result_all = m.populate_location_id(env)
print(f"✅ All migrated: {result_all['successful']}")

# 6. ตรวจสอบผลลัพธ์
remaining = env['stock.valuation.layer'].search_count([('location_id', '=', False)])
print(f"Remaining: {remaining}")
```

### ทดสอบหลัง Migration

```bash
# Run test suite
exec(open('/opt/instance1/odoo17/custom-addons/test_transit_migration.py').read())
```

## การทำงานของ Transit Location

### สถานการณ์ที่ 1: โอนระหว่างคลังสินค้า
```
คลัง A → Transit Location → คลัง B
```

**Step 1:** คลัง A → Transit
- ✅ Layer ติดลบที่ คลัง A (ของออก)
- ✅ Layer บวกที่ Transit Location (ของกำลังส่ง)

**Step 2:** Transit → คลัง B
- ✅ Layer ติดลบที่ Transit Location (ของออกจาก Transit)
- ✅ Layer บวกที่ คลัง B (ของเข้า)

### สถานการณ์ที่ 2: รับจากซัพพลายเออร์ผ่าน Transit
```
Supplier → Transit Location → คลังสินค้า
```

### สถานการณ์ที่ 3: ส่งให้ลูกค้าผ่าน Transit
```
คลังสินค้า → Transit Location → Customer
```

## ฟังก์ชัน Migration ที่มีให้ใช้

| ฟังก์ชัน | วัตถุประสงค์ | เมื่อใช้ |
|---------|------------|---------|
| `analyze_transit_locations()` | วิเคราะห์ Transit | ก่อน migrate |
| `populate_transit_location_layers()` | Migrate เฉพาะ Transit | มี Transit ในระบบ |
| `populate_location_id()` | Migrate ทั้งหมด | Migration หลัก |
| `populate_location_id_by_context()` | Migrate แบบเร็ว | ข้อมูลสะอาด |

## ตรวจสอบผลลัพธ์

### SQL Queries สำหรับตรวจสอบ

```sql
-- ตรวจสอบว่ามี Layer ไหนที่ยังไม่มี location
SELECT COUNT(*) FROM stock_valuation_layer WHERE location_id IS NULL;

-- นับ Layer แยกตามประเภท Location
SELECT 
    sl.usage as location_type,
    COUNT(*) as layer_count,
    SUM(svl.quantity) as total_qty
FROM stock_valuation_layer svl
JOIN stock_location sl ON svl.location_id = sl.id
GROUP BY sl.usage;

-- ดู Transit Layers
SELECT COUNT(*) 
FROM stock_valuation_layer svl
JOIN stock_location sl ON svl.location_id = sl.id
WHERE sl.usage = 'transit';
```

## เอกสารอ้างอิง

### เอกสารหลัก
- 📘 **[README.md](stock_fifo_by_location/README.md)** - คู่มือหลักของ Module
- 📗 **[TRANSIT_LOCATION_MIGRATION_GUIDE.md](stock_fifo_by_location/TRANSIT_LOCATION_MIGRATION_GUIDE.md)** - คู่มือ Migration แบบละเอียด
- 📙 **[TRANSIT_MIGRATION_QUICKREF.md](stock_fifo_by_location/TRANSIT_MIGRATION_QUICKREF.md)** - Quick Reference

### ไฟล์สำคัญ
- 🔧 **migrations/populate_location_id.py** - Script migration หลัก
- 🧪 **test_transit_migration.py** - Script ทดสอบ

## Troubleshooting

### ปัญหา: มี Layer ล้มเหลวจำนวนมาก

**วิธีแก้:**
```python
# ดู Layer ที่ล้มเหลว
failed_layers = env['stock.valuation.layer'].browse(result['failed_ids'])
for layer in failed_layers[:5]:
    print(f"Layer {layer.id}: {layer.product_id.name}")
    if layer.stock_move_id:
        move = layer.stock_move_id
        print(f"  Move: {move.location_id.name} → {move.location_dest_id.name}")
```

### ปัญหา: ไม่พบ Transit Location

**วิธีแก้:**
```python
# ตรวจสอบว่ามี Transit Location ในระบบ
transit_locs = env['stock.location'].search([('usage', '=', 'transit')])
print(f"Found {len(transit_locs)} transit locations:")
for loc in transit_locs:
    print(f"  - {loc.name}")
```

## ขั้นตอนที่แนะนำ

### 1. ก่อน Migration
- [ ] Backup database
- [ ] ทดสอบใน staging environment ก่อน
- [ ] อ่านเอกสารให้เข้าใจ

### 2. ระหว่าง Migration
- [ ] Run analyze_transit_locations() ก่อน
- [ ] Run populate_transit_location_layers() สำหรับ Transit
- [ ] Run populate_location_id() สำหรับส่วนที่เหลือ
- [ ] ตรวจสอบ failed layers

### 3. หลัง Migration
- [ ] Run test suite
- [ ] ตรวจสอบด้วย SQL queries
- [ ] ทดสอบการโอนระหว่างคลัง
- [ ] บันทึกปัญหา (ถ้ามี)

## คำสั่งเดียวจบ (One-Liner)

```python
# ⚠️ ใช้ด้วยความระมัดระวัง - แนะนำให้รันทีละขั้นตอน
from odoo.addons.stock_fifo_by_location.migrations import populate_location_id as m; a=m.analyze_transit_locations(env); t=m.populate_transit_location_layers(env); r=m.populate_location_id(env); print(f"Transit: {a['transit_locations']}, Success: {t['successful']+r['successful']}, Failed: {r['failed']}")
```

## ติดต่อ Support

หากพบปัญหา:
1. ตรวจสอบเอกสารที่เกี่ยวข้อง
2. รัน test script เพื่อวินิจฉัย
3. ตรวจสอบ Odoo logs
4. ติดต่อทีมพัฒนาพร้อมข้อมูล:
   - Odoo version
   - Error messages
   - Failed layer IDs
   - ประเภทของการเคลื่อนไหวที่มีปัญหา

---

**อัพเดทล่าสุด:** 17 พ.ย. 2568  
**Module Version:** 17.0.1.0.0  
**สถานะ:** ✅ พร้อมใช้งาน
