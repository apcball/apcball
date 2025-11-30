# คู่มือ Inventory Adjustment แบบแยก Warehouse

## โมดูล stock_fifo_by_location เวอร์ชัน 17.0.1.1.7

---

## ภาพรวม

ฟีเจอร์ Inventory Adjustment แบบแยก warehouse เป็นการขยายโมดูล `stock_fifo_by_location` เพื่อรองรับการปรับปรุง stock ที่เคารพขอบเขต warehouse และให้เลือกวิธีคิดต้นทุนได้อย่างยืดหยุ่น

### ความสามารถหลัก

1. **ปรับ Stock แยกตาม Warehouse**: ระบบติดตามการปรับแยกแต่ละ warehouse
2. **เลือก Cost Rule สำหรับการเพิ่ม Stock**: เลือกได้ว่าจะใช้ standard price, last purchase price, หรือกำหนดราคาเอง
3. **FIFO แยก Warehouse สำหรับการลด Stock**: ระบบตัด stock จาก warehouse ที่ถูกต้องโดยอัตโนมัติตามหักก FIFO
4. **Valuation ที่แม่นยำ**: สร้าง stock valuation layer ที่ถูกต้องพร้อม warehouse_id

---

## Cost Rule สำหรับการเพิ่ม Stock

เมื่อ**เพิ่ม stock** (นับได้มากกว่าในระบบ) คุณสามารถเลือกได้ว่าจะคิดมูลค่า stock ใหม่อย่างไร:

### 1. Standard Price (ค่าเริ่มต้น)

ใช้ราคามาตรฐานของสินค้าที่กำหนดไว้ในฟอร์มสินค้า

**ตัวอย่าง:**
- ราคามาตรฐานสินค้า: 100 บาท
- เพิ่ม: +10 ชิ้น
- **ผลลัพธ์**: สร้าง SVL ด้วย 100 บาท/ชิ้น = 1,000 บาท

**ใช้เมื่อไหร่:**
- เป็นค่าเริ่มต้น
- เมื่อใช้ standard costing เป็นหลัก
- สำหรับการตั้งค่า stock ครั้งแรก

### 2. Last Purchase Price (ราคาซื้อล่าสุด)

ใช้ราคาซื้อล่าสุด**ของ warehouse นั้นๆ เท่านั้น**

**ตัวอย่าง:**
- การรับของล่าสุดที่ WH-A: 5 ชิ้น ราคา 120 บาท/ชิ้น
- ปรับที่ WH-A: +10 ชิ้น
- **ผลลัพธ์**: สร้าง SVL ด้วย 120 บาท/ชิ้น = 1,200 บาท

**ใช้เมื่อไหร่:**
- ต้องการสะท้อนราคาตลาดปัจจุบัน
- มีประวัติการซื้อล่าสุด
- แต่ละ warehouse มีราคาซื้อต่างกัน

**Fallback:** ถ้าไม่มีประวัติการซื้อใน warehouse นั้น จะใช้ standard price แทน

### 3. Manual Cost (กำหนดเอง)

ใส่ต้นทุนต่อหน่วยด้วยตนเอง

**ตัวอย่าง:**
- ใส่ต้นทุนเอง: 150 บาท
- เพิ่ม: +10 ชิ้น
- **ผลลัพธ์**: สร้าง SVL ด้วย 150 บาท/ชิ้น = 1,500 บาท

**ใช้เมื่อไหร่:**
- นับพบ stock ชำรุด/ลดราคา
- สถานการณ์พิเศษที่ต้องใส่ราคาเอง
- ปรับจากแหล่งต้นทุนภายนอกที่ทราบแน่ชัด

**การตรวจสอบ:** ต้นทุนที่ใส่ต้องมากกว่า 0

---

## การตัด FIFO สำหรับการลด Stock

เมื่อ**ลด stock** (นับได้น้อยกว่าในระบบ) ระบบจะใช้ `_run_fifo()` แบบแยก warehouse อัตโนมัติ

### วิธีการทำงาน

1. ระบบหา warehouse จาก location ที่นับ
2. เรียก `_run_fifo()` พร้อม warehouse context
3. ตัด stock layer **เฉพาะ warehouse นั้น** ตามลำดับ FIFO
4. สร้าง negative SVL ด้วยต้นทุนที่ถูกตัด

### ตัวอย่างสถานการณ์

**ข้อมูล:**
- WH-A มี 2 layer:
  - Layer 1: 10 ชิ้น ราคา 100 บาท/ชิ้น (เก่ากว่า)
  - Layer 2: 10 ชิ้น ราคา 150 บาท/ชิ้น (ใหม่กว่า)

**การปรับ:**
- ลด stock 5 ชิ้นที่ WH-A

**ผลลัพธ์:**
- ตัด 5 ชิ้นจาก Layer 1 (FIFO - เก่าก่อน)
- Negative SVL: -5 ชิ้น ราคา 100 บาท/ชิ้น = -500 บาท
- Layer 1 คงเหลือ: 5 ชิ้น
- Layer 2 ไม่ถูกแตะต้อง: 10 ชิ้น

**การแยก Warehouse:**
- Layer จาก warehouse อื่น **ไม่ถูกตัดเด็ดขาด**
- แต่ละ warehouse มี FIFO queue แยกกัน

---

## การใช้งานจริง

### ตัวอย่าง 1: นับ Stock ใช้ Standard Price

**สถานการณ์:** นับพบสินค้าเพิ่ม 10 ชิ้น

**ขั้นตอน:**
1. เปิด inventory adjustment ที่ WH-A/Stock
2. นับได้ 10 ชิ้น (ระบบแสดง 0)
3. ปล่อยให้เป็น "Standard Price"
4. Validate

**ผลลัพธ์:**
- +10 ชิ้นใน stock
- SVL: +10 ชิ้น @ standard price

### ตัวอย่าง 2: นับใช้ Last Purchase Price

**สถานการณ์:** คลัง B รับของเมื่อสัปดาห์ที่แล้วราคา 120 บาท/ชิ้น ตอนนี้มานับ stock

**ขั้นตอน:**
1. เปิด inventory adjustment ที่ WH-B/Stock
2. นับได้ 25 ชิ้น (ระบบแสดง 20)
3. เลือก cost rule เป็น "Last Purchase Price (This Warehouse)"
4. Validate

**ผลลัพธ์:**
- +5 ชิ้นใน stock
- SVL: +5 ชิ้น @ 120 บาท/ชิ้น (จากการรับล่าสุด)

### ตัวอย่าง 3: ของชำรุด - Manual Cost

**สถานการณ์:** พบของชำรุด 8 ชิ้น มูลค่าเหลือแค่ 50 บาท/ชิ้น (ปกติ 100 บาท)

**ขั้นตอน:**
1. เปิด inventory adjustment
2. นับได้ 8 ชิ้น (ระบบแสดง 0)
3. เลือก cost rule เป็น "Manual Cost"
4. ใส่ต้นทุน: 50 บาท
5. Validate

**ผลลัพธ์:**
- +8 ชิ้นใน stock
- SVL: +8 ชิ้น @ 50 บาท/ชิ้น = 400 บาท

### ตัวอย่าง 4: Stock ลด

**สถานการณ์:** ระบบแสดง 20 ชิ้น แต่นับจริงได้ 15 ชิ้น

**ขั้นตอน:**
1. เปิด inventory adjustment ที่ WH-A/Stock
2. นับได้ 15 ชิ้น (ระบบแสดง 20)
3. Validate

**พฤติกรรมของระบบ:**
- รัน `_run_fifo()` สำหรับ WH-A อัตโนมัติ
- ตัด 5 ชิ้นเก่าสุดจาก layer ของ WH-A
- สร้าง negative SVL ด้วยต้นทุน FIFO

**ผลลัพธ์:**
- -5 ชิ้นใน stock
- SVL: -5 ชิ้น @ ต้นทุนจาก layer เก่าสุดของ WH-A

---

## หน้าจอการใช้งาน

### ฟอร์ม Inventory Adjustment

เมื่อสร้าง inventory adjustment จะเห็น:

**ส่วน Cost Configuration** (สำหรับการเพิ่ม stock):
```
┌─────────────────────────────────────────┐
│ Cost Configuration (for increases)      │
├─────────────────────────────────────────┤
│ Cost Rule: [Standard Price       ▼]    │
│ Manual Unit Cost: [         ]           │
└─────────────────────────────────────────┘
```

**ตัวเลือก Cost Rule:**
1. **Standard Price**: ใช้ product.standard_price
2. **Last Purchase Price (This Warehouse)**: ใช้ราคาซื้อล่าสุดของ warehouse นี้
3. **Manual Cost**: เปิดให้ใส่ "Manual Unit Cost" เอง

---

## กฎการตรวจสอบ

### การตรวจสอบ Cost Rule

1. **Manual Cost ต้องมีค่า**: ถ้าเลือก "manual" ต้องใส่ราคา > 0
2. **ต้องมี Warehouse สำหรับ Last Purchase**: Location ต้องเชื่อมกับ warehouse
3. **จำนวนต้องเป็นบวก**: จำนวนที่ปรับต้องเป็นบวก (ระบบจัดการเพิ่ม/ลดให้เอง)

### การตรวจสอบ Warehouse

1. **Location ต้องมี Warehouse**: Location ที่นับต้องเชื่อมกับ warehouse
2. **บังคับขอบเขต Warehouse**: การลดจะตัดเฉพาะ warehouse ที่ระบุเท่านั้น

---

## การทดสอบ

### รัน Test ทั้งหมด

```bash
python odoo-bin -c odoo.conf -d your_database \
  -i stock_fifo_by_location \
  --test-enable \
  --test-tags /stock_fifo_by_location:TestInventoryAdjustmentWarehouse \
  --stop-after-init
```

### รัน Test เฉพาะอัน

```bash
python odoo-bin -c odoo.conf -d your_database \
  --test-enable \
  --test-tags /stock_fifo_by_location:TestInventoryAdjustmentWarehouse.test_inventory_adjustment_increase_standard_price \
  --stop-after-init
```

---

## แก้ปัญหา

### ปัญหา: ไม่เห็นช่อง Manual Cost

**วิธีแก้:** ตรวจสอบว่าเลือก cost rule เป็น "Manual Cost" แล้ว

### ปัญหา: Last Purchase Price ออกมาเป็น Standard Price

**สาเหตุ:** ไม่มีประวัติการซื้อใน warehouse นี้  
**วิธีแก้:** เป็นพฤติกรรมที่ถูกต้อง - fallback ไปใช้ standard price ดู log จะมี warning

### ปัญหา: ตอนลด stock ใช้ราคาผิด

**สาเหตุ:** อาจมี layer เก่าๆ ใน database ที่ไม่มี warehouse_id  
**วิธีแก้:** รัน script ซ่อมแซม layer เพื่อเติม warehouse_id ให้ layer เก่าๆ

### ปัญหา: Error "Manual cost must be greater than zero"

**สาเหตุ:** เลือก manual cost แล้วแต่ไม่ได้ใส่ราคา  
**วิธีแก้:** ใส่ราคาที่ > 0 หรือเปลี่ยน cost rule

---

## สรุปสั้นๆ

### เวลาเพิ่ม Stock (นับได้มากกว่าระบบ):
- เลือกได้ว่าจะใช้ราคาไหน: standard / last purchase / manual
- ระบบสร้าง positive SVL ตาม warehouse ที่นับ

### เวลาลด Stock (นับได้น้อยกว่าระบบ):
- ระบบใช้ FIFO อัตโนมัติ
- ตัดจาก layer เก่าสุดของ warehouse นั้นๆ เท่านั้น
- สร้าง negative SVL ด้วยต้นทุน FIFO

### ขอบเขต Warehouse:
- **แยกกันอย่างเด็ดขาด**
- WH-A ไม่ไปตัดของจาก WH-B
- แต่ละ warehouse มี FIFO queue ของตัวเอง

---

## Migration จากเวอร์ชันเก่า

### จาก 17.0.1.1.6 → 17.0.1.1.7

**การเปลี่ยนแปลง Database:**
- เพิ่ม field ใหม่ใน stock_quant (inventory_cost_rule, inventory_manual_cost)
- เพิ่ม field ใหม่ใน stock_move (warehouse_id)

**ขั้นตอน Migration:**
1. Upgrade module: `odoo-bin -u stock_fifo_by_location`
2. ไม่ต้อง migrate data (field ใหม่มีค่า default)
3. ทดสอบบน environment ทดลองก่อน
4. Deploy production

**ความเข้ากันได้:**
- ✅ Layer เก่าๆ ไม่เปลี่ยนแปลง
- ✅ Move เก่าๆ ทำงานปกติ
- ✅ Cost rule default คือ "standard" (เหมือนเดิม)

---

## เอกสารอ้างอิง

- [INVENTORY_ADJUSTMENT_IMPLEMENTATION_GUIDE.md](INVENTORY_ADJUSTMENT_IMPLEMENTATION_GUIDE.md) - คู่มือภาษาอังกฤษฉบับเต็ม
- [STOCK_FIFO_BY_LOCATION_FIX_v17.0.1.1.5.md](STOCK_FIFO_BY_LOCATION_FIX_v17.0.1.1.5.md) - FIFO แยก warehouse พื้นฐาน
- [CROSS_WAREHOUSE_RETURN_TH.md](CROSS_WAREHOUSE_RETURN_TH.md) - การ return ข้าม warehouse

---

**เวอร์ชัน:** 17.0.1.1.7  
**อัพเดทล่าสุด:** 2024  
**โมดูล:** stock_fifo_by_location
