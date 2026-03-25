# Weekly Budget Control Module

## ภาพรวม (Overview)

**biz_weekly_budget** เป็นโมดูล Odoo 17 สำหรับควบคุมงบประมาณรายสัปดาห์สำหรับใบสั่งซื้อ (Purchase Orders), ใบขอซื้อ (Purchase Requisitions), และใบเบิกวัสดุ (Material Requisitions) โดยมีฟีเจอร์หลักคือการควบคุมยอดการใช้งาน (Used), ยอดจอง (Reserved), และการบล็อกการดำเนินการเมื่องบประมาณรายสัปดาห์ถูกใช้เกินกำหนด พร้อมระบบแดชบอร์ด (Dashboard) และการแจ้งเตือน

## คุณสมบัติหลัก (Key Features)

### 1. การจัดการแผนงบประมาณรายสัปดาห์ (Weekly Budget Plan Management)
- สร้างแผนงบประมาณรายสัปดาห์ด้วยช่วงวันที่กำหนดเอง
- สนับสนุนทั้งงบประมาณบริษัทเดียว หรือทุกบริษัท (Multi-company)
- สร้างรหัสอ้างอิงอัตโนมัติ (WB/YYYY/NNNN)
- สถานะเวิร์คโฟลว์: Draft → Confirmed → Done/Cancelled

### 2. การคำนวณงบประมาณแบบ 3 ส่วน (Budget Calculation: Used & Reserved)
- **ยอดงบประมาณทั้งหมด (Budget Limit):** งบประมาณที่ตั้งไว้ประจำสัปดาห์
- **ยอดใช้งานจริง (Used Amount):** คำนวณจาก Purchase Orders (PO) ที่ยืนยันแล้ว (สถานะ `purchase` หรือ `done`)
- **ยอดจองงบประมาณ (Reserved Amount):** คำนวณล่วงหน้าจาก:
  1. Purchase Requisitions (PR) ที่ไม่ใช่สถานะ draft
  2. Material Requisitions (MR) ที่ไม่ใช่สถานะ draft
  3. Standalone RFQs (PO สถานะ draft ที่ไม่ได้เชื่อมโยงกับ PR หรือ MR)
- **งบประมาณคงเหลือ (Available Amount):** คำนวณจาก `Budget Limit - Used Amount - Reserved Amount`

### 3. แดชบอร์ดสรุปข้อมูลงบประมาณ (OWL Smart Dashboard)
- แดชบอร์ดแบบโต้ตอบ (Interactive Dashboard) พัฒนาด้วยเทคโนโลยี OWL และ Chart.js
- แสดงกราฟเปรียบเทียบงบประมาณที่ตั้งไว้ ยอดใช้งาน ยอดจอง และยอดคงเหลือ (Limit vs Used vs Reserved)

### 4. การบล็อกการดำเนินการเมื่องบเกิน (Budget Exceed Blocking)
- **Purchase Orders**: บล็อกตอนกด "Send for Review" และ "Confirm"
- **Purchase Requisitions**: บล็อกตอนกด "Head Approve"
- **Material Requisitions**: บล็อกตอนกด "Submit"
- ระบบจะตรวจสอบทั้งยอด Used และยอดที่กำลังจะทำรายการ เพื่อป้องกันการใช้งบเกินกำหนด

### 5. ระบบแจ้งเตือน (Notification System)
- ส่งอีเมลแจ้งเตือนเมื่องบประมาณเกินกำหนด
- โพสต์ข้อความใน chatter ของแผนงบประมาณ
- กำหนดผู้รับแจ้งเตือนได้ในแผนงบประมาณ

### 6. การปรับงบประมาณและประวัติ (Budget Adjustment & History)
- Wizard สำหรับปรับงบประมาณรายสัปดาห์
- บันทึกประวัติการปรับเปลี่ยน (Adjustment History) พร้อมเหตุผลและผู้ทำรายการ
- สิทธิ์: Budget Manager เท่านั้นที่ปรับได้

## โครงสร้างโมดูล (Module Structure)

```
biz_weekly_budget/
├── models/
│   ├── weekly_budget_plan.py      # โมเดลแผนงบประมาณรายสัปดาห์
│   ├── weekly_budget_line.py      # โมเดลรายการงบประมาณรายสัปดาห์และการคำนวณยอด (Used/Reserved)
│   ├── purchase_order.py          # ส่วนขยาย PO (ตรวจสอบงบ)
│   ├── purchase_requisition.py    # ส่วนขยาย PR (ตรวจสอบและแสดงงบ)
│   ├── material_requisition.py    # ส่วนขยาย MR (ตรวจสอบและแสดงงบ)
│   └── weekly_budget_report.py    # โมเดลสำหรับรายงาน
├── wizard/
│   └── budget_adjustment_wizard.py # Wizard ปรับงบประมาณ
├── views/
│   ├── weekly_budget_plan_views.xml
│   ├── weekly_budget_line_views.xml
│   ├── purchase_order_views.xml
│   ├── purchase_requisition_views.xml
│   ├── material_requisition_views.xml
│   ├── dashboard_views.xml        # วิวสำหรับแสดง Dashboard
│   ├── weekly_budget_report_views.xml
│   └── menu_views.xml
├── static/src/                    # โค้ดสำหรับ OWL Dashboard
│   ├── js/budget_dashboard.js
│   ├── scss/budget_dashboard.scss
│   └── xml/budget_dashboard.xml
├── security/
│   ├── budget_security.xml       # กลุ่มผู้ใช้และ Record Rules
│   └── ir.model.access.csv       # สิทธิ์การเข้าถึง
└── data/
    ├── sequence_data.xml          # Sequence สำหรับรหัสอ้างอิง
    └── mail_template_data.xml     # เทมเพลตอีเมลแจ้งเตือน
```

## การติดตั้ง (Installation)

### Dependencies
- `web` - สำหรับ OWL Dashboard
- `purchase` - ใบสั่งซื้อ
- `mail` - ระบบอีเมลและการแจ้งเตือน
- `employee_purchase_requisition` - ใบขอซื้อพนักงาน
- `job_costing_management` - การจัดการต้นทุนงาน (สำหรับ Material Requisition)
- `buz_po_portal` - พอร์ทัลใบสั่งซื้อ (สำหรับ Send for Review)

### ขั้นตอนการติดตั้ง
1. คัดลอกโฟลเดอร์ `biz_weekly_budget` ไปยัง `custom-addons/`
2. รีสตาร์ท Odoo service
3. อัปเดตรายการแอป: Settings > Apps > Update Apps List
4. ค้นหา "Weekly Budget Control" และกด Install หรือ Upgrade

## การใช้งาน (Usage Guide)

### 1. ดูภาพรวมงบประมาณผ่าน Dashboard
**เส้นทาง:** Purchase > Budget Control > Dashboard
- ตรวจสอบสถานะการใช้งบประมาณรายสัปดาห์ผ่านกราฟ (Chart.js)
- ดูเปรียบเทียบยอด Limit, Used, และ Reserved ได้ในมุมมองเดียว

### 2. สร้างและจัดการแผนงบประมาณรายสัปดาห์
**เส้นทาง:** Purchase > Budget Control > Weekly Budget Plans
1. กด **Create** เพื่อสร้างแผนงบประมาณใหม่
2. กรอกข้อมูลช่วงวันที่ (Date From/To), บริษัท (Company/All Companies) และ Default Weekly Amount
3. กำหนด **Notify Users** ที่จะได้รับอีเมลแจ้งเตือน
4. กด **Generate Weeks** เพื่อสร้างงบประมาณรายสัปดาห์ย่อย (จันทร์ - อาทิตย์)
5. กด **Confirm** เพื่อเปิดใช้งานแผน

### 3. ตรวจสอบการใช้งานและยอดจอง (Used & Reserved)
**เส้นทาง:** Purchase > Budget Control > Budget Lines
- ดูรายการงบย่อยรายสัปดาห์ พร้อมสถานะ (Normal / Exceeded)
- ระบบจำแนกยอดค่าใช้จ่ายเป็น:
  - **Used Amount**: ยืนยัน PO แล้ว
  - **Reserved Amount**: ติดสถานะดำเนินการใน PR, MR, หรือ RFQ
  - **Available**: ยอดคงเหลือที่ใช้งานได้จริง
- ปรับเพิ่ม/ลดงบประมาณรายสัปดาห์ (เฉพาะ Budget Manager) โดยกดปุ่ม **Adjust**

### 4. การทำงานร่วมกับระบบจัดซื้อ (PO, PR, MR)
ระบบจะตรวจสอบจาก **Expected Payment (Payment Date)** ที่สัมพันธ์กับสัปดาห์นั้นๆ:
- **ในหน้าแบบฟอร์ม (Form View):** สามารถกดแท็บ **Budget Check** เพื่อประเมินยอดก่อนยืนยันระบบได้
- **การดำเนินการ (Action Validation):**
  - **PO** (Send for Review / Confirm): จะนำยอดไปคำนวณหักลบกับงบประมาณที่เหลือ หากเกินจะถูกบล็อก
  - **PR** (Head Approve): ตรวจสอบยอด Reserved งบประมาณ หากการอนุมัติทำให้ยอดจองงบประมาณเกิน จะถูกบล็อก
  - **MR** (Submit): ตรวจสอบงบประมาณในลักษณะเดียวกับ PR

## การตั้งค่า (Configuration)

### วันที่ที่ใช้ในการดึงงบประมาณ (Payment Date)
โมดูลนี้ใช้แนวคิด **Expected Payment** หรือ `payment_date` เป็นหลักในการคำนวณจับคู่กับสัปดาห์ของงบประมาณ:
- **Purchase Orders**: ประเมินจากรอบเครดิตการจ่ายเงิน หรืออิงจากคาดการณ์ +30 วัน
- **Purchase Requisitions**: อิงจาก Requisition Deadline หรือวันที่ขอซื้อ +30 วัน
- **Material Requisitions**: อิงจาก Required Date +30 วัน

## สิทธิ์การใช้งาน (User Permissions)

- **Budget User**: ดูข้อมูลงบประมาณและ Dashboard ได้ แต่แก้ไขไม่ได้
- **Budget Manager**: สร้างแผน, ดู Dashboard, และมีปุ่มปรับงบประมาณ (Adjust Budget) พร้อมเขียนคำอธิบาย
- **Purchase Users**: มีสิทธิ์ดูข้อมูล budget lines เพื่อให้ทำงานร่วมกับ PO/PR/MR ได้

## การแก้ไขปัญหา (Troubleshooting)

### ยอดงบประมาณไม่อัปเดตชั่วคราว
ในบางกรณีที่ข้อมูลมีการแก้ไขย้อนหลังจากระบบภายนอก สามารถกดปุ่ม **Recompute Used** ใน Weekly Budget Plan เพื่อบังคับให้ระบบคำนวณยอด Used และ Reserved ใหม่ 100%

### สร้าง PO แล้วไม่พบงบประมาณ
- ตรวจสอบฟิลด์ `Expected Payment` ของเอกสาร ว่าอยู่ในช่วงวันที่ของแผนงบประมาณ (Weekly Budget Plan) ที่ Confirmed แล้วหรือไม่
- ตรวจสอบ Company ตรงกับเอกสาร หรือเลือกแผนงานเป็น All Companies หรือยัง

---
**หมายเหตุ**: โมดูลนี้พัฒนาขึ้นสำหรับระบบควบคุมงบประมาณ (KYLD) เน้นแนวคิดการแบ่งงบออกเป็นรายสัปดาห์และคำนวณ Expected Cash Outflow ผ่าน `payment_date` (Expected Payment).
