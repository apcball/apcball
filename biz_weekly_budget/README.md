# Weekly Budget Control Module

## ภาพรวม (Overview)

**biz_weekly_budget** เป็นโมดูล Odoo 17 สำหรับควบคุมงบประมาณรายสัปดาห์สำหรับใบสั่งซื้อ (Purchase Orders), ใบขอซื้อ (Purchase Requisitions), ใบเบิกวัสดุ (Material Requisitions), คลังพัสดุรวม (Procurement Pool) และ ระบบบัญชี (Vendor Bills) โดยมีฟีเจอร์หลักคือการควบคุมยอดการใช้งาน (Used), ยอดจอง (Reserved), และการบล็อกการดำเนินการเมื่องบประมาณรายสัปดาห์ถูกใช้เกินกำหนด พร้อมระบบแดชบอร์ด (Dashboard) และการแจ้งเตือน

โมดูลนี้ใช้แนวคิด **Accrual / Cashflow Budget Hybrid** โดยจำแนกอย่างชัดเจนระหว่างงบประมาณที่ถูกจองไว้ (Commitment) และงบประมาณที่มีกำหนดจ่ายชำระจริง (Cashflow)

### ระบบ Budget Move Ledger (ระบบบัญชีงบประมาณ)
โมดูลนี้ใช้ `budget.move` เป็นบัญชี ledger กลางในการติดตามการเคลื่อนไหวของงบประมาณทั้งหมด ทำให้สามารถ:
- ติดตามประวัติการใช้งบทั้งหมดได้อย่างละเอียด
- รองรับการคำนวณแบบ multi-dimensional (analytic account + department)
- รองรับการตั้งเบิกบิลแบบ partial และยกเลิกบิลอัตโนมัติ

## คุณสมบัติหลัก (Key Features)

### 1. การจัดการแผนงบประมาณรายสัปดาห์ (Weekly Budget Plan Management)
- สร้างแผนงบประมาณรายสัปดาห์ด้วยช่วงวันที่กำหนดเอง
- สนับสนุนทั้งงบประมาณบริษัทเดียว หรือทุกบริษัท (Multi-company)
- สร้างรหัสอ้างอิงอัตโนมัติ (WB/YYYY/NNNN)
- สถานะเวิร์คโฟลว์: Draft → Confirmed → Done/Cancelled

### 2. การคำนวณงบประมาณแบบ 3 ส่วน (Budget Calculation)
- **ยอดงบประมาณทั้งหมด (Budget Limit):** งบประมาณที่ตั้งไว้ประจำสัปดาห์ (รองรับการจัดสรรตาม analytic account และ department)
- **ยอดใช้งานจริง (Used Amount):** คำนวณจาก **Vendor Bills (Invoices)** ที่สร้างขึ้น (อิงจาก `invoice_date_due` หรือวันที่ครบกำหนดชำระ)
- **ยอดจองงบประมาณ (Reserved Amount):** คำนวณล่วงหน้าจาก:
  1. Purchase Requisitions (PR) ที่อนุมัติแล้ว
  2. Material Requisitions (MR) ที่ส่งคำขอแล้ว
  3. Standalone RFQs (PO สถานะ draft ที่ไม่ได้เชื่อมโยงกับ PR/MR)
  4. Purchase Orders (PO) ที่ยืนยันแล้ว (แต่ยังไม่ได้สร้าง Vendor Bill ทั้งหมด)
  5. Procurement Pools ที่ confirmed แล้ว
- **งบประมาณคงเหลือ (Available Amount):** คำนวณจาก `Budget Limit - Used Amount - Reserved Amount`

> **หมายเหตุ:** เมื่อมีการตั้งเบิก (Create Vendor Bill) ยอด Reserved จาก PO จะถูกเปลี่ยนเป็นยอด Used แบบอัตโนมัติ (และรองรับการทยอยตั้งเบิก Partial Bills)
>
> **Vendor Credit Notes:** รองรับการบันทึกยอดคืนงบประมาณเมื่อมีการสร้างบิลเครดิต (in_refund) จะทำให้ยอด Used ลดลงตามจำนวน

### 3. แดชบอร์ดสรุปข้อมูลงบประมาณ (OWL Smart Dashboard)
- แดชบอร์ดแบบโต้ตอบ (Interactive Dashboard) พัฒนาด้วยเทคโนโลยี OWL และ Chart.js
- แสดงกราฟเปรียบเทียบงบประมาณที่ตั้งไว้ ยอดจอง และยอดค่าใช้จ่ายที่คาดว่าจะเกิดขึ้นจริง (Limit vs Reserved vs Forecasted Cashflow/Used)

### 4. การบล็อกการดำเนินการเมื่องบเกิน (Budget Exceed Blocking)
- **Purchase Orders**: บล็อกตอนกด "Send for Review" และ "Confirm"
- **Purchase Requisitions**: บล็อกตอนกด "Head Approve"
- **Material Requisitions**: บล็อกตอนกด "Submit"
- **Procurement Pools**: บล็อกตอนกด "Confirm" และ "Create RFQ"
- ระบบจะตรวจสอบยอดคงเหลือ (Available) ก่อนทำการอนุมัติ เพื่อป้องกันการใช้งบเกินกำหนด

### 5. ระบบแจ้งเตือนและการขออนุมัติงบพิเศษ (Notification & Approval System)
- ส่งอีเมลแจ้งเตือนเมื่องบประมาณเกินกำหนดไปยัง Budget Managers
- โพสต์ข้อความใน chatter ของแผนงบประมาณและเอกสารที่เกี่ยวข้อง (PO/PR/MR)
- กำหนดผู้รับแจ้งเตือนได้ในแผนงบประมาณ

#### Budget Approval Request (การขออนุมัติงบพิเศษ)
เมื่อเอกสารต้องการใช้งบเกินกำหนด ผู้ขอสามารถ:
1. สร้าง Budget Approval Request พร้อมระบุเหตุผล
2. ระบบจะแจ้งเตือน Budget Managers อัตโนมัติ
3. Budget Managers สามารถอนุมัติหรือปฏิเสธพร้อมระบุเหตุผล
4. หลังจากอนุมัติ ผู้ขอสามารถดำเนินการต่อได้
5. สถานะการขออนุมัติจะแสดงบนเอกสารต้นทาง (PO/PR/MR)

### 6. การปรับงบประมาณและประวัติ (Budget Adjustment & History)
- Wizard สำหรับปรับงบประมาณรายสัปดาห์
- บันทึกประวัติการปรับเปลี่ยน (Adjustment History) พร้อมเหตุผลและผู้ทำรายการ
- สิทธิ์: Budget Manager เท่านั้นที่ปรับได้

## โครงสร้างโมดูล (Module Structure)

```text
biz_weekly_budget/
├── models/
│   ├── weekly_budget_plan.py        # โมเดลแผนงบประมาณรายสัปดาห์ (Plan header)
│   ├── weekly_budget_line.py        # โมเดลรายการงบประมาณและคำนวณยอด (Used/Reserved/Available)
│   ├── weekly_budget_allocation.py  # โมเดลการจัดสรรงบตาม analytic account
│   ├── budget_move.py               # Budget Ledger - บันทึกการเคลื่อนไหวของงบทั้งหมด
│   ├── budget_approval_request.py   # โมเดลการขออนุมัติงบพิเศษ
│   ├── weekly_budget_report.py      # SQL View สำหรับรายงานวิเคราะห์งบประมาณ
│   ├── purchase_order.py            # ส่วนขยาย PO + การคำนวณ Reserved/Used
│   ├── purchase_requisition.py      # ส่วนขยาย PR + การคำนวณ Reserved
│   ├── material_requisition.py      # ส่วนขยาย MR + การคำนวณ Reserved
│   ├── procurement_pool.py         # ส่วนขยาย Procurement Pool + การคำนวณ Reserved
│   └── account_move.py              # ส่วนขยาย Vendor Bill สำหรับคำนวณ Used
├── wizard/
│   ├── budget_adjustment_wizard.py    # Wizard ปรับงบประมาณ
│   └── budget_reason_wizards.py       # Wizards สำหรับขอและอนุมัติงบพิเศษ
├── controllers/
│   └── budget_api.py                # API endpoints สำหรับ Dashboard และ Matrix Planner
├── views/
│   ├── weekly_budget_plan_views.xml
│   ├── weekly_budget_line_views.xml
│   ├── weekly_budget_report_views.xml
│   ├── budget_approval_request_views.xml
│   ├── purchase_order_views.xml
│   ├── purchase_requisition_views.xml
│   ├── material_requisition_views.xml
│   ├── procurement_pool_views.xml
│   ├── dashboard_views.xml           # วิวสำหรับแสดง Dashboard
│   └── menu_views.xml
├── static/src/                      # โค้ดสำหรับ OWL Dashboard & Matrix Planner
│   ├── js/
│   │   ├── budget_dashboard.js        # OWL Dashboard component
│   │   └── budget_matrix_planner.js   # Budget Matrix Planner
│   ├── scss/
│   │   ├── budget_dashboard.scss
│   │   └── budget_matrix_planner.scss
│   └── xml/
│       ├── budget_dashboard.xml
│       └── budget_matrix_planner.xml
├── security/
│   ├── budget_security.xml          # กลุ่มผู้ใช้และ Record Rules
│   └── ir.model.access.csv          # สิทธิ์การเข้าถึง
└── data/
    ├── sequence_data.xml             # Sequence สำหรับรหัสอ้างอิง
    └── mail_template_data.xml        # เทมเพลตอีเมลแจ้งเตือน
```

## การติดตั้ง (Installation)

### Dependencies
- `web` - สำหรับ OWL Dashboard & Matrix Planner
- `purchase` - ใบสั่งซื้อ
- `mail` - ระบบอีเมลและการแจ้งเตือน (chatter, notifications)
- `employee_purchase_requisition` - ใบขอซื้อพนักงาน (PR)
- `job_costing_management` - การจัดการต้นทุนงาน (สำหรับ Material Requisition)
- `buz_po_portal` - พอร์ทัลใบสั่งซื้อ (สำหรับ Send for Review workflow)

### ขั้นตอนการติดตั้ง
1. คัดลอกโฟลเดอร์ `biz_weekly_budget` ไปยัง `custom-addons/`
2. รีสตาร์ท Odoo service
3. อัปเดตรายการแอป: Settings > Apps > Update Apps List
4. ค้นหา "Weekly Budget Control" และกด Install หรือ Upgrade

## การใช้งาน (Usage Guide)

### 1. ดูภาพรวมงบประมาณผ่าน Dashboard
**เส้นทาง:** Purchase > Budget Control > Dashboard
- ตรวจสอบสถานะการใช้งบประมาณรายสัปดาห์ผ่านกราฟ (Chart.js)
- ดูเปรียบเทียบยอด Limit, Used (เงินจ่ายจริง/บิลแจ้งหนี้), Reserved (ยอดผูกพัน) และ Available
- กรองข้อมูลตาม Plan, Year, หรือ Month

### 2. สร้างและจัดการแผนงบประมาณรายสัปดาห์
**เส้นทาง:** Purchase > Budget Control > Weekly Budget Plans

**สร้างแผนงบประมาณใหม่:**
1. กด **Create** เพื่อสร้างแผนงบประมาณใหม่
2. เลือก **Month** และ **Year** (ระบบจะคำนวณ Date From/To อัตโนมัติ)
3. เลือก **Company** หรือเลือก **All Companies**
4. กรอกข้อมูลงบประมาณ:
   - **Default Weekly Amount**: ยอดงบประมาณเริ่มต้นต่อสัปดาห์ (ถ้าไม่มี allocation)
   - หรือกำหนด **Total Budget (Plan)** และ **Analytic Allocations**
5. กำหนด **Notify Users** ที่จะได้รับอีเมลแจ้งเตือน
6. กด **Generate Weeks** เพื่อสร้างงบประมาณรายสัปดาห์ย่อย (จันทร์ - อาทิตย์)
7. กด **Confirm** เพื่อเปิดใช้งานแผน

**การจัดสรรงบประมาณแบบ Analytic Allocation:**
1. ในแผนงบประมาณ กด **Add a line** ใน Analytic Allocations
2. เลือก **Analytic Account** (จำเป็น)
3. เลือก **Department** (ถ้าต้องการ)
4. ระบุ **Percentage** (รวมทั้งหมดต้องเท่ากับ 100%)
5. กด Generate Weeks เพื่อกระจายงบตามสัดส่วน

### 3. ตรวจสอบการใช้งานและยอดจอง (Used & Reserved)
**เส้นทาง:** Purchase > Budget Control > Budget Lines

**ดูรายการงบย่อย:**
- ดูรายการงบย่อยรายสัปดาห์ พร้อมสถานะ (Normal / Exceeded)
- ระบบจำแนกยอดค่าใช้จ่ายเป็น:
  - **Used Amount**: บิล (Vendor Bill) ที่ถูกสร้างแล้ว
  - **Reserved Amount**: ติดสถานะดำเนินการใน PR, MR, RFQ, Procurement Pool และ PO ที่ยังไม่ได้ออกบิล
  - **Available**: ยอดคงเหลือที่ใช้งานได้จริง (Limit - Used - Reserved)

**ปรับเพิ่ม/ลดงบประมาณ:**
1. เลือก Budget Line ที่ต้องการ
2. กดปุ่ม **Adjust** (เฉพาะ Budget Manager)
3. กรอก New Budget Amount และ Reason
4. ระบบจะบันทึกประวัติการปรับและแจ้งเตือนผู้ที่เกี่ยวข้อง

**ดู Budget Moves:**
- กด Smart Button "Budget Moves" เพื่อดูรายการการเคลื่อนไหวของงบประมาณทั้งหมด
- ระบุ Source Model, Source ID, Amount และ Move Type (Used/Reserved)

### 4. การทำงานร่วมกับระบบจัดซื้อ
ระบบคำนวณยอดโควตางบประมาณตามสัดส่วนการชำระหรือยอดที่เหลือ:
- ระบบจะแสดง Budget Check Result บนแต่ละเอกสาร
- เมื่องบเกินกำหนด ระบบจะ:
  1. แจ้งเตือนผ่าน UI (Budget Warning)
  2. แสดง wizard ให้กรอกเหตุผลเพื่อขออนุมัติพิเศษ
  3. สร้าง Budget Approval Request อัตโนมัติ

### 5. จัดการ Budget Approval Requests
**เส้นทาง:** Purchase > Budget Control > Budget Approval Requests

**สำหรับ Budget Managers:**
1. ดูรายการคำขอที่รอการอนุมัติ (Pending)
2. เลือกคำขอและตรวจสอบรายละเอียด
3. กด **Approve** หรือ **Reject**
4. กรอกเหตุผลใน wizard
5. ระบบจะแจ้งผู้ขอทราบผลการตัดสินใจ

**สำหรับ Requesters:**
- ดูสถานะของคำขอของตนเอง
- ดูเหตุผลที่ Manager ให้มา (ถ้าถูกปฏิเสธ)
- หลังจากอนุมัติ สามารถดำเนินการเอกสารต้นทางต่อได้

### 6. ใช้งาน Budget Matrix Planner
**เส้นทาง:** Purchase > Budget Control > Budget Matrix Planner
- แสดงงบประมาณแบบ matrix (Weeks x Analytic Accounts)
- แก้ไขยอดงบได้โดยตรงใน cell
- ดูภาพรวมการใช้งบได้ทันที

### 7. รายงานงบประมาณ (Budget Reports)
**เส้นทาง:** Purchase > Budget Control > Budget Reports
- รายงานวิเคราะห์งบประมาณรายสัปดาห์ (SQL View based)
- แสดงข้อมูล Budget Limit, Actual Spending, Remaining, และ Utilization %
- รองรับการกรองข้อมูลตามวันที่, บริษัท, และ Analytic Account

## การตั้งค่า (Configuration)

### วันที่ที่ใช้ในการดึงงบประมาณ (Target Date / Cashflow Projection)
โมดูลนี้ใช้แนวคิด **Cash Outflow Date** ในการผูกข้อมูลเข้ากับสัปดาห์:
- **Vendor Bill**: อิงจาก `invoice_date_due` (วันครบกำหนดชำระ)
- **Purchase Orders**: อิงจาก `payment_date` (Expected Payment Date) - คำนวณจาก Payment Terms หรือ Order Date + 30 วัน
- **Purchase Requisitions**: อิงจาก `payment_date` - คำนวณจาก Requisition Deadline + 30 วัน
- **Material Requisitions**: อิงจาก `payment_date` - คำนวณจาก Required Date + 30 วัน
- **Procurement Pool**: อิงจาก `payment_date` - คำนวณจาก Create Date + 30 วัน

> **หมายเหตุ:** ทุกเอกสารสามารถแก้ไข Payment Date ได้ด้วยตนเอง (Manual Override)

### การจัดสรรงบประมาณ (Budget Allocation)
โมดูลรองรับการจัดสรรงบประมาณใน 2 รูปแบบ:
1. **Simple Allocation:** ใช้ Default Weekly Amount เดียวสำหรับทุกสัปดาห์
2. **Analytic Allocation:** จัดสรรตาม Analytic Account และ Department
   - กำหนด Percentage สำหรับแต่ละ Analytic Account
   - ระบบจะกระจายงบประมาณตามสัดส่วนไปยังแต่ละสัปดาห์

### Analytic Distribution
ระบบรองรับการแบ่งส่วนงบประมาณแบบ multi-dimensional:
- ใช้ `analytic_distribution` field จากเอกสารต้นทาง (PO Line, Bill Line, PR Line, MR Line)
- ถ้าไม่มี analytic_distribution จะใช้ `analytic_account_id` จากเอกสารหรือ department_id จากเอกสารต้นทาง
- ทำให้สามารถติดตามงบประมาณตามแต่ละ Analytic Account ได้อย่างแม่นยำ

### Workflow การขออนุมัติงบพิเศษ (Budget Approval Request)
เมื่อเอกสารถูกบล็อกเนื่องจากงบไม่เพียงพอ:

1. **ผู้ขอ (Requester)**
   - ระบบจะแสดง wizard ให้กรอกเหตุผล
   - สร้าง Budget Approval Request
   - ระบบส่งอีเมลแจ้งเตือนไปยัง Budget Managers
   - เอกสารต้นทางจะแสดงสถานะ "Pending Approval"

2. **Budget Manager**
   - รับอีเมลแจ้งเตือนเมื่อมีคำขอใหม่
   - เข้าไปที่ Budget Approval Request
   - ตรวจสอบรายละเอียด:
     - Document Type & Reference
     - Budget Week & Amount Details
     - Requester's Reason
   - เลือกอนุมัติหรือปฏิเสธ พร้อมระบุเหตุผล

3. **หลังการอนุมัติ**
   - ผู้ขอได้รับแจ้งผลการตัดสินใจ
   - เอกสารต้นทางสามารถดำเนินการต่อได้ (Send for Review, Confirm, Submit)
   - ยอดงบประมาณจะถูกบันทึกแยกจาก regular budget

### เอกสารที่รองรับการขออนุมัติงบพิเศษ
- **Purchase Requisition (PR)**: เมื่อกด Head Approve
- **Material Requisition (MR)**: เมื่อกด Submit
- **Purchase Order (PO)**: เมื่อกด Send for Review หรือ Confirm

## สิทธิ์การใช้งาน (User Permissions)

- **Budget User**: ดูข้อมูลงบประมาณและ Dashboard ได้ แต่แก้ไขไม่ได้
- **Budget Manager**: สร้างแผน, ดู Dashboard, และมีปุ่มปรับงบประมาณ (Adjust Budget) พร้อมเขียนคำอธิบาย
- **Purchase Users**: มีสิทธิ์ดูข้อมูล budget lines เพื่อให้ทำงานร่วมกับ PO/PR/MR ได้

## การแก้ไขปัญหา (Troubleshooting)

### ยอดงบประมาณไม่อัปเดตชั่วคราว
ในบางกรณีที่ข้อมูลมีการแก้ไขย้อนหลังจากระบบภายนอก สามารถกดปุ่ม **Recompute Used** ใน Weekly Budget Plan เพื่อบังคับให้ระบบคำนวณยอด Used และ Reserved ใหม่ 100%

### Global Recompute (การคำนวณงบประมาณทั้งหมดใหม่)
หากต้องการบั้งคับคำนวณงบประมาณทั้งหมดใหม่ (ใช้ในกรณีมีการแก้ไขข้อมูลจำนวนมาก):
- เข้าไปที่ Weekly Budget Plan ใดๆ
- กดปุ่ม **Recompute Used** (ระบบจะทำการ:
  1. ลบ budget.move records ทั้งหมด
  2. สร้าง budget.move ใหม่จาก PR, MR, PO, Bill ทั้งหมด
  3. คำนวณยอด Used/Reserved ใหม่ทั้งหมด)

### สร้างเอกสารแล้วไม่พบงบประมาณ
- ตรวจสอบฟิลด์วันที่รับรู้การจ่ายเงิน (Expected Payment Date / Due Date) ว่าอยู่ในช่วงวันที่ของแผนงบประมาณที่ Confirmed แล้วหรือไม่
- ตรวจสอบ Company ตรงกับเอกสาร หรือเลือกแผนงานเป็น All Companies หรือยัง
- ตรวจสอบ Analytic Account และ Department ตรงกับ Budget Lines หรือไม่

### ยอด Reserved ไม่ถูกต้องหลังจากสร้าง PO จาก PR/MR
เมื่อ PO ถูกสร้างจาก PR/MR:
- PO จะสร้าง Reserved moves ของตัวเอง
- PR/MR จะลบ Reserved moves ของตัวเอง (เพราะ PO เข้ามารับผิดชอบแทน)
- หากมีปัญหาสามารถกด Recompute Used เพื่อแก้ไข

### Bill ถูกยกเลิกแต่ยอดไม่ถูกคืน
- ตรวจสอบว่า Bill ถูก cancel หรือ set to draft แล้ว
- ระบบจะทำการ:
  1. ลบ budget.move (used) ของ Bill
  2. คำนวณ Reserved moves ของ PO ใหม่ (ถ้า PO มียอด remaining to bill)
- หากยังไม่ถูกต้อง ให้กด Recompute Used

## API Endpoints

### `/budget/api/dashboard_data`
ข้อมูลสำหรับ OWL Dashboard
- **Parameters:**
  - `selectedPlanId`: (optional) Filter by specific plan
  - `selectedYear`: (optional) Filter by year
  - `selectedMonth`: (optional) Filter by month
- **Returns:** Summary data, weekly breakdown, and pie chart data

### `/budget/api/matrix`
ข้อมูลสำหรับ Budget Matrix Planner
- **Parameters:**
  - `plan_id`: ID of the budget plan
- **Returns:** Matrix data organized by weeks and analytic accounts/departments

### `/budget/api/update_cell`
อัปเดตยอดงบประมาณใน Matrix Planner
- **Parameters:**
  - `line_id`: ID of the budget line
  - `amount_limit`: New budget amount
- **Returns:** Success/error status

---
**หมายเหตุ**: โมดูลนี้เป็นการยกระดับการจัดการงบประมาณแบบ **Commitment Budget + Cashflow Budget** ทำให้ตัวเลขงบประมาณสะท้อนกระแสเงินสดขาออกในอนาคต (Cash Outflow Forecast) ได้อย่างแม่นยำยิ่งขึ้น
