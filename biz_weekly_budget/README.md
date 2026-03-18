# Weekly Budget Control (Mogen)

## ภาพรวม (Overview)

**biz_weekly_budget** เป็นโมดูล Odoo 17 สำหรับควบคุมงบประมาณรายสัปดาห์สำหรับใบสั่งซื้อ (Purchase Orders) และใบขอซื้อ (Purchase Requisitions) โดยมีฟีเจอร์หลักคือการบล็อกการดำเนินการเมื่องบประมาณรายสัปดาห์ถูกใช้เกินกำหนด พร้อมระบบ Dashboard อัจฉริยะสำหรับติดตามงบประมาณแบบ Real-time

## คุณสมบัติหลัก (Key Features)

### 1. การจัดการแผนงบประมาณรายสัปดาห์ (Weekly Budget Plan Management)
- สร้างแผนงบประมาณรายสัปดาห์ด้วยช่วงวันที่กำหนดเอง
- สนับสนุนทั้งงบประมาณบริษัทเดียว หรือทุกบริษัท (Multi-company)
- สร้างรหัสอ้างอิงอัตโนมัติ (WB/YYYY/NNNN)
- สถานะเวิร์คโฟลว์: Draft → Confirmed → Done/Cancelled

### 2. การสร้างงบประมาณรายสัปดาห์อัตโนมัติ (Auto-generate Weekly Lines)
- สร้างงบประมาณรายสัปดาห์อัตโนมัติจากช่วงวันที่ (Monday-Sunday)
- กำหนดงบประมาณเริ่มต้นรายสัปดาห์ได้
- แสดงสถานะ: Normal / Exceeded
- คำนวณยอดใช้งานจริง (Used) และยอดจอง (Reserved) อัตโนมัติ

### 3. ระบบ Dashboard อัจฉริยะ (Modern OWL Smart Dashboard)
- แสดงข้อมูลสรุปงบประมาณในรูปแบบกราฟ (Chart.js)
- ติดตามยอด Budget Limit, Actual Spending, และ Reserved (PR/RFQ)
- ตัวกรองข้อมูลตามปี และแผนงบประมาณ
- ตารางสรุปรายสัปดาห์พร้อมสถานะการใช้งบ

### 4. การจองงบประมาณ (Reserved Amount Logic)
- **Reserved Amount**: คำนวณจากใบขอซื้อ (PR) ที่ไม่ใช่สถานะ Draft และใบสั่งซื้อที่ยังเป็น RFQ (Standalone)
- ป้องกันการใช้จ่ายเกินงบตั้งแต่ขั้นตอนการวางแผน
- ระบบจะหักยอด Reserved ออกเมื่อ RFQ ถูกยืนยันเป็น Purchase Order (ยอดจะย้ายไปที่ Used แทน)

### 5. การบล็อกการดำเนินการเมื่องบเกิน (Budget Exceed Blocking)
- **Purchase Orders**: บล็อกตอนกด "Send for Review" และ "Confirm"
- **Purchase Requisitions**: บล็อกตอนกด "Head Approve"
- แสดงข้อความแจ้งเตือนพร้อมรายละเอียดการเกินงบ

### 6. ระบบแจ้งเตือน (Notification System)
- ส่งอีเมลแจ้งเตือนไปยังผู้รับผิดชอบเมื่องบประมาณเกินกำหนด
- โพสต์ข้อความแจ้งเตือนใน Chatter ของแผนงบประมาณอัตโนมัติ
- กำหนดรายชื่อผู้รับแจ้งเตือน (Notify Users) ได้ในแต่ละแผน

### 7. การปรับงบประมาณ (Budget Adjustment)
- Wizard สำหรับปรับงบประมาณรายสัปดาห์ (เฉพาะ Budget Manager)
- บันทึกประวัติการปรับเปลี่ยน (Adjustment History) พร้อมเหตุผลและผู้อนุมัติ

## โครงสร้างโมดูล (Module Structure)

```
biz_weekly_budget/
├── models/
│   ├── weekly_budget_plan.py      # โมเดลแผนงบประมาณรายสัปดาห์
│   ├── weekly_budget_line.py      # โมเดลรายการงบประมาณรายสัปดาห์
│   ├── weekly_budget_report.py    # โมเดลรายงานและ View สำหรับ Dashboard
│   ├── purchase_order.py          # ส่วนขยาย PO (ตรวจสอบและบล็อกงบ)
│   └── purchase_requisition.py    # ส่วนขยาย PR (ตรวจสอบและบล็อกงบ)
├── wizard/
│   └── budget_adjustment_wizard.py # Wizard สำหรับการปรับงบประมาณ
├── views/
│   ├── weekly_budget_plan_views.xml
│   ├── weekly_budget_line_views.xml
│   ├── weekly_budget_report_views.xml
│   ├── dashboard_views.xml        # วิวสำหรับ Smart Dashboard
│   ├── purchase_order_views.xml
│   ├── purchase_requisition_views.xml
│   └── menu_views.xml
├── static/
│   └── src/                       # OWL Component & Dashboard Assets (JS/XML/SCSS)
├── security/
│   ├── budget_security.xml        # กลุ่มผู้ใช้ (User/Manager) และ Record Rules
│   └── ir.model.access.csv        # สิทธิ์การเข้าถึงโมเดล
└── data/
    ├── sequence_data.xml          # Sequence สำหรับรหัส WB
    └── mail_template_data.xml     # เทมเพลตอีเมลแจ้งเตือนงบเกิน
```

## การติดตั้ง (Installation)

### Dependencies
- `purchase` (Standard Odoo)
- `mail` (Standard Odoo)
- `employee_purchase_requisition` (Custom Module)
- `buz_po_portal` (Custom Module)

### ขั้นตอนการติดตั้ง
1. คัดลอกโฟลเดอร์ `biz_weekly_budget` ไปยัง `custom-addons/`
2. รีสตาร์ท Odoo Service
3. อัปเดตรายการแอป: Settings > Apps > Update Apps List
4. ค้นหา "Weekly Budget Control (Mogen)" และกด Install

## การใช้งาน (Usage Guide)

### 1. การตั้งค่าแผนงบประมาณ
- ไปที่ **Purchase > Budget Control > Weekly Budget Plans**
- สร้างแผนใหม่ กำหนดวันที่ เริ่มต้น-สิ้นสุด และบริษัท
- กำหนด **Notify Users** ที่จะได้รับอีเมลแจ้งเตือน
- กด **Generate Weeks** เพื่อสร้างรายการงบประมาณรายสัปดาห์อัตโนมัติ
- ตรวจสอบและแก้ไข Budget Limit ในแต่ละสัปดาห์ (ถ้าจำเป็น) แล้วกด **Confirm**

### 2. การใช้งาน Smart Dashboard
- ไปที่ **Purchase > Budget Control > Smart Dashboard**
- ดูภาพรวมการใช้งบประมาณทั้งระบบ
- ใช้ตัวกรองด้านบนเพื่อดูข้อมูลรายปี หรือรายแผนงบประมาณ

### 3. การตรวจสอบงบในเอกสาร
- ในหน้า **Purchase Order** หรือ **Purchase Requisition** จะมีแท็บ **Budget Check**
- กดปุ่ม **Check Budget** เพื่อดูสถานะงบประมาณปัจจุบัน
- ระบบจะแสดงยอด: **Used** (ใช้จริง), **Reserved** (จองไว้), และ **Available** (ที่เหลืออยู่)

## สิทธิ์การใช้งาน (User Permissions)

- **Budget User**: ดูแผนงบประมาณ รายการงบ และ Dashboard ได้
- **Budget Manager**: สามารถสร้าง/แก้ไข/ลบ แผนงบประมาณ และใช้งาน Wizard ปรับงบประมาณได้
- **Purchase User**: สามารถดูข้อมูลในแท็บ Budget Check ของ PO/PR เพื่อตรวจสอบงบก่อนยืนยัน

## เวอร์ชันและความเข้ากันได้ (Version & Compatibility)

- **Odoo Version**: 17.0
- **Module Version**: 17.0.1.0.0
- **License**: LGPL-3
- **Author**: APCBALL / KYLD

---
*Note: โมดูลนี้พัฒนาขึ้นเพื่อเพิ่มประสิทธิภาพในการควบคุมต้นทุนการจัดซื้อขององค์กร*
