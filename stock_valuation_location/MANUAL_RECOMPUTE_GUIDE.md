# คู่มือการ Recompute Location ด้วยตนเอง

## วิธีการ Recompute (3 วิธี)

### 1. Recompute ทั้งหมด (ผ่าน Menu)

**ขั้นตอน:**
1. ไปที่ `Inventory > Configuration > Recompute SVL Locations`
2. คลิกที่ menu นี้
3. ระบบจะ recompute ทั้งหมดอัตโนมัติ
4. แสดงผลลัพธ์เมื่อเสร็จสิ้น

**เหมาะสำหรับ:**
- Recompute records ทั้งหมดครั้งเดียว
- หลังจาก upgrade module
- เมื่อต้องการ refresh ข้อมูลทั้งหมด

---

### 2. Recompute แบบเลือก Records (ผ่าน List View)

**ขั้นตอน:**
1. ไปที่ `Inventory > Reporting > Inventory Valuation`
2. เลือก records ที่ต้องการ recompute (checkbox)
3. คลิก `Action` > `Recompute Location`
4. แสดงผลลัพธ์เมื่อเสร็จสิ้น

**เหมาะสำหรับ:**
- Recompute เฉพาะ records ที่ต้องการ
- แก้ไขข้อมูลเฉพาะบางส่วน
- ทดสอบการทำงาน

---

### 3. Recompute ผ่าน Python Code (สำหรับ Developer)

**วิธีที่ 3.1: Recompute ทั้งหมด**
```python
# เข้า Odoo shell
./odoo-bin shell -d your_database

# Recompute ทั้งหมด
svl = env['stock.valuation.layer'].search([('stock_move_id', '!=', False)])
svl.action_recompute_location()
```

**วิธีที่ 3.2: Recompute เฉพาะที่ location_id ว่าง**
```python
# Recompute เฉพาะที่ยังไม่มี location
svl = env['stock.valuation.layer'].search([
    ('stock_move_id', '!=', False),
    ('location_id', '=', False)
])
svl.action_recompute_location()
```

**วิธีที่ 3.3: Recompute แบบ manual batch**
```python
# แบบกำหนด batch size เอง
svl = env['stock.valuation.layer'].search([('stock_move_id', '!=', False)])
batch_size = 500

for i in range(0, len(svl), batch_size):
    batch = svl[i:i+batch_size]
    batch._compute_location_id()
    env.cr.commit()
    print(f"Processed {min(i+batch_size, len(svl))}/{len(svl)}")
```

---

## คุณสมบัติของ Function

### `action_recompute_location()`

**พารามิเตอร์:**
- `self`: recordset ที่ต้องการ recompute (ถ้าว่างจะ recompute ทั้งหมด)

**การทำงาน:**
1. ตรวจสอบว่ามี records หรือไม่
2. ถ้าไม่มี records (เรียกจาก menu) จะค้นหาทั้งหมด
3. แบ่งเป็น batch ๆ ละ 1000 records
4. Recompute แต่ละ batch
5. Commit หลังจาก recompute แต่ละ batch
6. แสดงผลลัพธ์และจำนวน records ที่ process

**ข้อดี:**
- ✅ ปลอดภัย: ไม่ใช้ SQL โดยตรง
- ✅ Memory efficient: แบ่ง batch เพื่อไม่ให้ใช้ memory มากเกินไป
- ✅ Transaction safe: Commit ทุก batch
- ✅ Logging: บันทึก progress ใน log file
- ✅ User friendly: แสดง notification เมื่อเสร็จ

---

## Performance

**ความเร็วโดยประมาณ:**
- ~1,000 records: 5-10 วินาที
- ~10,000 records: 1-2 นาที
- ~100,000 records: 10-20 นาที
- ~300,000+ records: 1+ ชั่วโมง

**Tips สำหรับ Database ใหญ่:**
1. ทำใน off-peak hours
2. ตรวจสอบ log file เพื่อดู progress
3. อาจแบ่ง recompute เป็นช่วง (ใช้ filter)

---

## Troubleshooting

### ปัญหา: Timeout
**วิธีแก้:**
- Recompute ทีละส่วน (ใช้ filter ตาม date หรือ product)
- เพิ่ม `limit` ในการ search

### ปัญหา: Memory Error
**วิธีแก้:**
- ลด batch_size ใน code
- Restart Odoo service ก่อน recompute

### ปัญหา: ไม่มีผลลัพธ์
**ตรวจสอบ:**
- ต้องมี `stock_move_id` ในระเภบ
- Location ต้องเป็น `internal` usage
- ตรวจสอบ log file ว่ามี error หรือไม่

---

## Log Files

ระบบจะบันทึก progress ใน Odoo log file:

```bash
# ตรวจสอบ log
tail -f /var/log/odoo/odoo.log | grep "SVL"

# หรือถ้าใช้ systemd
journalctl -u odoo17 -f | grep "SVL"
```

**Log ที่จะเห็น:**
```
INFO Starting manual recompute for 15000 SVL records
INFO Recomputed 1000/15000 records
INFO Recomputed 2000/15000 records
...
INFO Recomputed 15000/15000 records
```

---

## ตัวอย่างการใช้งาน

### กรณีที่ 1: หลัง Upgrade Module
```bash
# 1. Upgrade module
./odoo-bin -u stock_valuation_location -d your_database --stop-after-init

# 2. Start Odoo
sudo systemctl start odoo17

# 3. ไปที่ UI > Inventory > Configuration > Recompute SVL Locations
```

### กรณีที่ 2: แก้ไขเฉพาะ Product บางตัว
```python
# Shell
svl = env['stock.valuation.layer'].search([
    ('product_id', 'in', [123, 456, 789]),
    ('stock_move_id', '!=', False)
])
svl.action_recompute_location()
```

### กรณีที่ 3: แก้ไขเฉพาะช่วงเวลา
```python
# Shell
from datetime import datetime
svl = env['stock.valuation.layer'].search([
    ('create_date', '>=', '2024-01-01'),
    ('create_date', '<=', '2024-12-31'),
    ('stock_move_id', '!=', False)
])
svl.action_recompute_location()
```

---

## สรุป

✅ **3 วิธีการ recompute:**
1. Menu (ทั้งหมด)
2. Action button (เลือก records)
3. Python code (ยืดหยุ่นที่สุด)

✅ **ปลอดภัยและมีประสิทธิภาพ:**
- Batch processing
- Transaction commits
- Progress logging
- Error handling

✅ **ใช้งานง่าย:**
- Click เดียวจาก UI
- แสดงผลลัพธ์ชัดเจน
