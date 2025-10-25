# คู่มือการแก้ไขปัญหา Stock Layer Usage Compatibility

## ภาพรวม

การแก้ไขนี้แก้ปัญหาความเข้ากันได้ระหว่าง 2 modules:
- **buz_valuation_regenerate** - สร้าง Stock Valuation Layers ใหม่
- **stock_valuation_layer_usage** - ติดตามการใช้งาน Stock Valuation Layers

## ไฟล์ที่ถูกแก้ไข

### 1. buz_valuation_regenerate

#### ไฟล์ใหม่:
- `models/stock_valuation_layer.py` - Override model เพื่อจัดการ context และ cleanup

#### ไฟล์ที่แก้ไข:
- `models/__init__.py` - เพิ่ม import stock_valuation_layer
- `models/valuation_regenerate_wizard.py` - เพิ่ม context เมื่อสร้างและลบ SVL
- `__manifest__.py` - อัพเดทเวอร์ชั่นเป็น 17.0.1.3.0

### 2. stock_valuation_layer_usage

#### ไฟล์ที่แก้ไข:
- `models/stock_valuation_layer.py` - เพิ่มการตรวจสอบ context
- `__manifest__.py` - อัพเดทเวอร์ชั่นเป็น 17.0.1.2.0

## การติดตั้ง/อัพเกรด

### วิธีที่ 1: ใช้สคริปต์อัตโนมัติ (แนะนำ)

```bash
cd /opt/instance1/odoo17/custom-addons

# รันสคริปต์อัพเกรด
./upgrade_stock_layer_modules.sh your_database_name
```

สคริปต์จะ:
1. ตรวจสอบว่า modules ติดตั้งแล้วหรือไม่
2. เสนอให้ทำ backup database
3. อัพเกรด modules
4. แสดงผลลัพธ์

### วิธีที่ 2: อัพเกรดด้วยตนเอง

```bash
cd /opt/instance1/odoo17

# อัพเกรด modules
./odoo-bin -c odoo.conf -d your_database -u buz_valuation_regenerate,stock_valuation_layer_usage --stop-after-init

# Restart Odoo service
sudo systemctl restart odoo
```

## การทดสอบ

### 1. ทดสอบด้วยสคริปต์

```bash
cd /opt/instance1/odoo17/custom-addons

# รันสคริปต์ทดสอบ
python3 test_stock_layer_compatibility.py http://localhost:8069 your_database admin your_password
```

สคริปต์จะตรวจสอบ:
- ✓ เวอร์ชั่น modules
- ✓ Model inheritance
- ✓ Orphaned usage records

### 2. ทดสอบใน Odoo UI

#### ทดสอบ Regeneration:

1. ไปที่ **Inventory → Valuation → Re-Generate Valuation**
2. เลือก product ที่มี stock moves
3. ตั้งค่า:
   - Mode: Products
   - เลือก product(s)
   - Date From/To: ตามต้องการ
   - เปิด "Dry Run"
4. คลิก **"Compute Plan"**
5. ตรวจสอบว่าไม่มี error
6. ดูผลลัพธ์ใน preview
7. ปิด "Dry Run"
8. คลิก **"Apply Regeneration"**
9. ตรวจสอบว่า SVL ถูกสร้างใหม่สำเร็จ

#### ทดสอบ Usage Tracking:

1. สร้าง stock move ใหม่ (เช่น Purchase Receipt)
2. ไปที่ **Inventory → Valuation Layers**
3. เปิด SVL ที่เพิ่งสร้าง
4. ตรวจสอบว่ามี tab "Valuation Usage" และ "Incoming Valuation Usage"
5. ตรวจสอบว่า usage records ถูกสร้างถูกต้อง

### 3. ทดสอบการลบ Orphaned Records

```sql
-- Query เพื่อหา orphaned usage records
SELECT COUNT(*) 
FROM stock_valuation_layer_usage u
WHERE u.stock_valuation_layer_id NOT IN (
    SELECT id FROM stock_valuation_layer
)
OR u.dest_stock_valuation_layer_id NOT IN (
    SELECT id FROM stock_valuation_layer
);

-- ผลลัพธ์ควรเป็น 0
```

## การทำงาน

### Context Keys ที่ใช้:

1. **`valuation_regeneration=True`**
   - บอกว่าอยู่ในช่วง regeneration
   - ใช้โดย buz_valuation_regenerate

2. **`skip_usage_tracking=True`**
   - สั่งให้ข้าม usage tracking
   - ใช้โดย stock_valuation_layer_usage

### Flow การทำงาน:

#### Normal Operation (ไม่ใช่ regeneration):
```
Stock Move → SVL Create → Usage Tracking → Usage Records Created
```

#### Regeneration Operation:
```
Wizard Start
  → Delete Old SVLs (with context)
      → Cleanup Usage Records
  → Create New SVLs (with context)
      → Skip Usage Tracking
  → Done
```

## Troubleshooting

### ปัญหา: Error เมื่อรัน regeneration

**สาเหตุ:** modules ยังไม่ได้อัพเกรด

**แก้ไข:**
```bash
./upgrade_stock_layer_modules.sh your_database
sudo systemctl restart odoo
```

### ปัญหา: พบ Orphaned Usage Records

**สาเหตุ:** Regeneration รันก่อนอัพเกรด

**แก้ไข:**
```sql
-- ลบ orphaned records ด้วยตนเอง
DELETE FROM stock_valuation_layer_usage 
WHERE stock_valuation_layer_id NOT IN (
    SELECT id FROM stock_valuation_layer
)
OR dest_stock_valuation_layer_id NOT IN (
    SELECT id FROM stock_valuation_layer
);
```

### ปัญหา: Usage tracking ไม่ทำงาน

**ตรวจสอบ:**
1. เวอร์ชั่น stock_valuation_layer_usage >= 17.0.1.2.0
2. Operation ไม่ใช่ regeneration (ไม่มี context)
3. SVL มี stock_move_id

**แก้ไข:**
- อัพเกรด module
- Restart Odoo
- สร้าง stock move ใหม่

### ปัญหา: Module ไม่สามารถอัพเกรดได้

**ตรวจสอบ:**
1. File permissions
2. Python syntax errors
3. Database connection

**แก้ไข:**
```bash
# ตรวจสอบ syntax
cd /opt/instance1/odoo17/custom-addons
python3 -m py_compile buz_valuation_regenerate/models/*.py
python3 -m py_compile stock_valuation_layer_usage/models/*.py

# ตรวจสอบ permissions
ls -la buz_valuation_regenerate/models/
ls -la stock_valuation_layer_usage/models/

# ตรวจสอบ Odoo logs
tail -f /var/log/odoo/odoo-server.log
```

## Performance

### ผลกระทบต่อ Performance:

✅ **ดีขึ้น:**
- Regeneration เร็วขึ้นเพราะข้าม usage tracking
- ไม่มีการสร้าง usage records ที่ไม่จำเป็น
- Cleanup orphaned records อัตโนมัติ

⚠️ **ไม่เปลี่ยนแปลง:**
- Normal operations ทำงานเหมือนเดิม
- Usage tracking ทำงานปกติ

## ความเข้ากันได้

### Odoo Version:
- ✅ Odoo 17.0

### Python Version:
- ✅ Python 3.8+
- ✅ Python 3.10+
- ✅ Python 3.12+

### Dependencies:
- ✅ stock
- ✅ account
- ✅ stock_landed_costs
- ✅ stock_account_product_run_fifo_hook

## การอัพเดทในอนาคต

หากต้องการเพิ่มฟีเจอร์ใหม่:

### ใน buz_valuation_regenerate:
```python
# เพิ่มใน models/stock_valuation_layer.py
def your_new_method(self):
    if self.env.context.get('valuation_regeneration'):
        # จัดการพิเศษสำหรับ regeneration
        pass
    return super().your_new_method()
```

### ใน stock_valuation_layer_usage:
```python
# เพิ่มใน models/stock_valuation_layer.py
def your_tracking_method(self):
    if self.env.context.get('skip_usage_tracking'):
        return  # ข้ามการ track
    # ประมวลผลปกติ
```

## สรุป

✅ **ได้ประโยชน์:**
- Modules ทำงานร่วมกันได้
- ไม่มี orphaned records
- Performance ดีขึ้น
- Maintenance ง่ายขึ้น

✅ **ไม่กระทบ:**
- Functionality ของแต่ละ module
- Data integrity
- Normal operations

## ติดต่อ

หากพบปัญหาหรือต้องการความช่วยเหลือ:
- ตรวจสอบ logs: `/var/log/odoo/odoo-server.log`
- รันสคริปต์ทดสอบ
- ดูเอกสารเพิ่มเติม: `STOCK_LAYER_USAGE_COMPATIBILITY_FIX.md`

---

**Modified by:** apcball  
**Date:** 25 ตุลาคม 2568  
**Version:** 1.0
