# คู่มือการใช้งาน Dispatch Report - Preprint Form

## ภาพรวม
โมดูลนี้ช่วยให้คุณสามารถพิมพ์ใบจ่ายสินค้าลงบนกระดาษต่อเนื่องแบบ Preprint ได้ โดยสามารถปรับตำแหน่งของข้อมูลต่างๆ ให้ตรงกับ form ที่พิมพ์มาแล้ว

## ฟีเจอร์หลัก
- ปรับตำแหน่งเลขที่เอกสารได้อิสระ
- ปรับตำแหน่งวันที่ได้อิสระ
- ปรับตำแหน่งข้อมูลลูกค้า (ชื่อ, ที่อยู่, เบอร์โทร)
- ปรับตำแหน่งข้อมูลรถ (ประเภท, ทะเบียน, คนขับ)
- ปรับตำแหน่งตารางสินค้า
- ปรับระยะห่างระหว่างแถวสินค้า
- ปรับตำแหน่งคอลัมน์ต่างๆ
- ปรับตำแหน่งลายเซ็น
- สามารถสร้างหลาย configuration สำหรับ form ที่แตกต่างกัน

## การติดตั้ง

1. อัพเกรดโมดูล:
   ```bash
   # เข้าไปที่ Odoo Apps
   # ค้นหา "Inventory Delivery Report"
   # คลิก Upgrade
   ```

2. หรือใช้คำสั่ง:
   ```bash
   cd /opt/instance1/odoo17
   ./odoo-bin -u buz_inventory_delivery_report -d your_database --stop-after-init
   ```

## การตั้งค่า

### 1. เข้าสู่หน้าตั้งค่า
- ไปที่: **Inventory > Configuration > Dispatch Report Config**

### 2. สร้าง Configuration ใหม่
- คลิก **Create**
- กรอกชื่อ Configuration (เช่น "Form Type A")
- เลือก **Is Default** หากต้องการให้เป็น configuration หลัก

### 3. ปรับตำแหน่งตามแท็บต่างๆ

#### แท็บ Header Positions
- **Document Number - Top**: ระยะจากด้านบน (px)
- **Document Number - Left**: ระยะจากด้านซ้าย (px)
- **Document Date - Top**: ระยะจากด้านบน (px)
- **Document Date - Left**: ระยะจากด้านซ้าย (px)

#### แท็บ Customer Info Positions
- **Customer Name**: ตำแหน่งชื่อลูกค้า
- **Customer Address**: ตำแหน่งที่อยู่ลูกค้า
- **Customer Phone**: ตำแหน่งเบอร์โทรลูกค้า

#### แท็บ Vehicle Info Positions
- **Vehicle Type**: ตำแหน่งประเภทรถ
- **Vehicle Plate**: ตำแหน่งทะเบียนรถ
- **Driver Name**: ตำแหน่งชื่อคนขับ

#### แท็บ Table Positions
- **Table Top**: ตำแหน่งด้านบนของตาราง
- **Table Left**: ตำแหน่งด้านซ้ายของตาราง
- **Line Height**: ความสูงของแต่ละแถว (px)
- **Column Offsets**: ตำแหน่งของแต่ละคอลัมน์
  - No. Column: เลขที่
  - Code Column: รหัสสินค้า
  - Name Column: ชื่อสินค้า
  - Qty Column: จำนวน
  - Unit Column: หน่วย
  - Remark Column: หมายเหตุ

#### แท็บ Footer Positions
- **Total Quantity**: ตำแหน่งยอดรวม
- **Sender Signature**: ตำแหน่งลายเซ็นผู้ส่ง
- **Receiver Signature**: ตำแหน่งลายเซ็นผู้รับ

#### แท็บ Page Settings
- **Font Size**: ขนาดตัวอักษร (px)
- **Font Family**: แบบฟอนต์
- **Page Width**: ความกว้างหน้ากระดาษ (px)
- **Page Height**: ความสูงหน้ากระดาษ (px)

## การใช้งาน

### พิมพ์รายงาน

1. ไปที่ **Inventory > Operations > Transfers**
2. เปิด Delivery Order ที่ต้องการพิมพ์
3. คลิก **Print > ใบจ่ายสินค้า**
4. ระบบจะสร้าง PDF ตามตำแหน่งที่ตั้งค่าไว้

### การปรับแต่งตำแหน่ง

1. **วิธีการหาตำแหน่งที่ถูกต้อง:**
   - พิมพ์ทดสอบครั้งแรก
   - วัดระยะจากขอบกระดาษถึงตำแหน่งที่ต้องการ
   - แปลงเป็น pixels (1 นิ้ว = 72 pixels ที่ DPI 90)
   - ปรับค่าใน Configuration
   - พิมพ์ทดสอบอีกครั้ง
   - ทำซ้ำจนกว่าจะตรงตำแหน่ง

2. **เทคนิคการปรับ:**
   - เริ่มจากปรับตำแหน่งพื้นฐานก่อน (เลขที่เอกสาร, วันที่)
   - ปรับตำแหน่งตารางสินค้า
   - ปรับระยะห่างระหว่างแถว (Line Height)
   - ปรับตำแหน่งคอลัมน์
   - สุดท้ายปรับส่วน footer

3. **Tips:**
   - ใช้ไม้บรรทัดวัดระยะจากขอบกระดาษ
   - เริ่มต้นด้วยค่า default แล้วค่อยๆ ปรับ
   - เปลี่ยนทีละ 5-10 pixels ในแต่ละครั้ง
   - บันทึก configuration ที่ใช้งานได้แล้วเป็นชื่ออื่น

## ตัวอย่างค่าที่ใช้งานได้

### กระดาษต่อเนื่อง Letter Size
- Page Width: 612 px
- Page Height: 792 px
- Font Size: 14 px
- Line Height: 28 px

### การปรับแต่งเพิ่มเติม

หากต้องการเพิ่มฟิลด์อื่นๆ:
1. แก้ไข `models/stock_picking.py` เพื่อเพิ่มฟิลด์
2. แก้ไข `models/dispatch_report_config.py` เพื่อเพิ่มตำแหน่ง
3. แก้ไข `report/dispatch_report.xml` เพื่อแสดงผล
4. แก้ไข `views/dispatch_report_config_views.xml` เพื่อเพิ่มช่องตั้งค่า

## การแก้ไขปัญหา

### ตำแหน่งไม่ตรง
- ตรวจสอบ DPI ของเครื่องพิมพ์ (ควรเป็น 90)
- ตรวจสอบ Page Settings ว่าตรงกับขนาดกระดาษ
- ลอง Upgrade โมดูลใหม่

### ไม่แสดงข้อมูล
- ตรวจสอบว่ามีข้อมูลในฟิลด์นั้นๆ หรือไม่
- ตรวจสอบ permissions
- ดู log ของ Odoo

### ฟอนต์ไม่ถูกต้อง
- ติดตั้ง TH Sarabun New font บนเครื่อง server
- หรือเปลี่ยน Font Family ในการตั้งค่า

## การสนับสนุน

หากมีปัญหาหรือข้อสงสัย กรุณาติดต่อทีมพัฒนา
