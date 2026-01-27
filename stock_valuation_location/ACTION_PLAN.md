# 🚨 URGENT: Stock Valuation Location Fix - Action Plan

## สถานการณ์
- ✅ วิเคราะห์ปัญหาเสร็จสิ้น
- ✅ แก้ไขโค้ดเรียบร้อย
- ⏳ รออัพเกรดและทดสอบ

## ปัญหาหลักที่พบ

### 1. N+1 Query Problem 
- Loop ทำงานทีละ record → query database หลายหมื่น-แสนครั้ง
- **แก้แล้ว:** ใช้ batch read query แค่ 2-3 ครั้ง

### 2. No Batch Processing
- โหลดข้อมูลทั้งหมดมาทำงานพร้อมกัน → Memory overflow
- **แก้แล้ว:** แบ่งทำงานทีละ 1000 records

### 3. No Timeout Protection  
- Query ค้างไม่จบ → Server hang
- **แก้แล้ว:** ตั้ง timeout 5 นาที (configurable)

## 🚀 ขั้นตอนดำเนินการ ทันที

### STEP 1: Backup (5 นาที) ⚠️ สำคัญมาก!
```bash
cd /opt/instance1/odoo17
sudo systemctl stop odoo17

# Backup database
sudo -u postgres pg_dump -Fc your_database_name > \
  /tmp/backup_stock_valuation_$(date +%Y%m%d_%H%M%S).dump
```

### STEP 2: Upgrade Module (10 นาที)
```bash
# อยู่ที่ /opt/instance1/odoo17
./odoo-bin -c odoo.conf -d your_database_name \
  -u stock_valuation_location --stop-after-init

# Start service
sudo systemctl start odoo17
```

### STEP 3: ตรวจสอบจำนวนข้อมูล (2 นาที)
```bash
# เข้า Odoo shell
./odoo-bin shell -c odoo.conf -d your_database_name

# ใน shell พิมพ์:
>>> count = env["stock.valuation.layer"].search_count([("stock_move_id", "!=", False)])
>>> print(f"Total SVL records to process: {count}")
>>> exit()
```

### STEP 4: Recompute Location Data (สำหรับ Database ใหญ่)

**ใช้ SQL Fast Path เท่านั้น** (เหมาะสำหรับ 300k+ records)

#### ขั้นตอนที่ 4.1: ทดสอบด้วย Dry Run
1. Login Odoo
2. ไปที่: **Inventory → Configuration → SVL Location — Fast SQL**
3. ตั้งค่า:
  - ✅ **Dry run**: เปิด (ทดสอบก่อน)
  - **Limit**: default 20000 (configured in wizard; adjust down if memory is limited)
  - **Timeout**: default 600 seconds (configured in wizard; increase if your server can handle larger batches)
4. คลิก **Run**
5. ดูจำนวน "Affected rows" - นี่คือจำนวน records ที่จะได้รับผลกระทบ

#### ขั้นตอนที่ 4.2: Run จริงทีละ Batch
1. เปลี่ยน **Dry run** เป็น **ปิด**
2. ตั้ง **Limit** = 10000-50000 (แนะนำ 20000 สำหรับ 369k records)
3. ตั้ง **Timeout** = 300-600 (ขึ้นกับขนาด server)
4. คลิก **Run** ซ้ำๆ จนกว่า **Affected rows = 0**

**ตัวอย่างสำหรับ 369k records:**
```
Run ครั้งที่ 1:  Affected rows: 20000 ← ยังไม่เสร็จ
Run ครั้งที่ 2:  Affected rows: 20000 ← ยังไม่เสร็จ  
Run ครั้งที่ 3:  Affected rows: 20000 ← ยังไม่เสร็จ
...
Run ครั้งที่ 18: Affected rows: 9362  ← ใกล้เสร็จ
Run ครั้งที่ 19: Affected rows: 0     ← เสร็จสมบูรณ์ ✅
```

**หมายเหตุ:** สำหรับ 369,362 records ใช้เวลาประมาณ 30-60 นาที

### STEP 5: Verify (3 นาที)
1. ไปที่: **Inventory → Reporting → Stock Valuation**
2. ตรวจสอบว่ามี column "Location"
3. ทดสอบ Filter และ Group By Location
4. ตรวจสอบข้อมูลถูกต้อง

## 📊 เวลาโดยประมาณ (SQL Fast Path)

| จำนวน Records | Limit | เวลาโดยประมาณ | Batch Runs |
|--------------|-------|---------------|------------|
| 100,000 | 10000 | 15-20 นาที | 10 runs |
| 250,000 | 20000 | 25-35 นาที | 13 runs |
| **369,362** | **20000** | **30-60 นาที** | **~19 runs** |
| 500,000 | 20000 | 45-75 นาที | 25 runs |
| 1,000,000 | 50000 | 1-2 ชั่วโมง | 20 runs |

**หมายเหตุ:** เวลาขึ้นกับ server specs (CPU, RAM, Disk I/O)

## 🔍 Monitoring ระหว่างทำงาน

เปิด terminal ใหม่และ run:
```bash
# ดู log real-time
tail -f /var/log/odoo/instance1.log | grep "SVL location"
```

คุณจะเห็น:
```
INFO: Starting SVL location recompute for 250000 records in batches of 1000
INFO: Processed 1000/250000 SVL records
INFO: Processed 2000/250000 SVL records
...
```

## ⚠️ คำเตือนและข้อควรระวัง

1. **ห้าม skip backup** - ถึงแม้จะมีการทดสอบแล้วก็ตาม
2. **รัน off-peak time** - ถ้ามีข้อมูลเยอะ ควรรันตอนไม่มี user ใช้งาน
3. **ไม่ต้อง restart ระหว่าง recompute** - ปล่อยให้ทำงานจนจบ
4. **Monitor memory/CPU** - ถ้า server มี RAM น้อย (<4GB) ควรลด limit ลง
5. **Cron job ยังปิดอยู่** - ไม่ต้องกังวลว่าจะ run ซ้ำ

## 🐛 Troubleshooting ฉุกเฉิน

### ถ้า Server ค้างระหว่างทำงาน
```bash
# 1. Restart Odoo
sudo systemctl restart odoo17

# 2. ตรวจสอบ memory
free -h

# 3. ตรวจสอบ PostgreSQL
sudo systemctl status postgresql

# 4. ถ้ายังค้าง - restart PostgreSQL (ระวัง!)
sudo systemctl restart postgresql
sudo systemctl restart odoo17
```

### ถ้าเกิด Error
1. เช็ค log: `/var/log/odoo/instance1.log`
2. เช็ค PostgreSQL log: `/var/log/postgresql/postgresql-XX-main.log`
3. Restore จาก backup ถ้าจำเป็น:
```bash
sudo systemctl stop odoo17
sudo -u postgres pg_restore -d your_database_name backup_file.dump
sudo systemctl start odoo17
```

## 📁 ไฟล์ที่แก้ไขแล้ว

```
✅ models/stock_valuation_layer.py          - Fixed N+1, added batching, timeout
✅ wizards/stock_valuation_location_fast_sql_wizard.py - Added timeout field
✅ views/stock_valuation_location_fast_sql_wizard_views.xml - Updated UI
✅ __manifest__.py                          - Bumped version, removed ORM recompute
❌ data/stock_valuation_recompute_action.xml - REMOVED (not suitable for large DB)
❌ data/ir_cron_recompute_location.xml      - REMOVED (not suitable for large DB)
```

**หมายเหตุ:** ORM Recompute และ Cron job ถูกลบออกเนื่องจาก:
- ไม่เหมาะสำหรับ database ขนาดใหญ่ (300k+ records)
- มีความเสี่ยงต่อ memory overflow และ timeout
- SQL Fast Path มีประสิทธิภาพดีกว่ามากสำหรับข้อมูลจำนวนมาก

## 📞 หากมีปัญหา

1. **ดู log ก่อนเสมอ** - ส่วนใหญ่หาสาเหตุได้จาก log
2. **ทดสอบด้วย dry run** - ก่อน run จริง
3. **ลด batch size/limit** - ถ้า server อ่อนแรง
4. **Restore จาก backup** - ถ้าเกิดปัญหาร้ายแรง

## 📚 เอกสารอ้างอิง

- `FIX_SUMMARY.md` - รายละเอียดทางเทคนิค (ภาษาอังกฤษ)
- `README_TH.md` - คู่มือใช้งานแบบละเอียด (ภาษาไทย)
- `upgrade_module.sh` - Script อัพเกรดอัตโนมัติ
- `test_performance.py` - Script ทดสอบ performance

## ✅ Checklist

- [ ] Backup database เรียบร้อย
- [ ] Upgrade module สำเร็จ
- [ ] ตรวจสอบจำนวน records (369,362 records)
- [ ] Run SQL Fast Path Dry Run
- [ ] ดู Affected rows จาก Dry Run
- [ ] Run SQL Fast Path จริง (limit 20000)
- [ ] Run ซ้ำจนกว่า Affected rows = 0
- [ ] Verify ผลลัพธ์ใน Stock Valuation
- [ ] Test filter และ group by location
- [ ] Monitor log ไม่มี error
- [ ] เอกสารบันทึกผลการทำงาน

---

**Status:** ✅ Ready for deployment
**Risk Level:** 🟡 Medium (มี backup = ปลอดภัย)
**Time Required:** 30 นาที - 3 ชั่วโมง (ขึ้นกับขนาดข้อมูล)
**Last Updated:** 25 October 2568

🚀 **เริ่มได้เลย! Good luck!**
