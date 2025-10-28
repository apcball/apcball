Prompt Engineering: Implement Odoo 17 Module - IT Request Suite

🎯 Objective

สร้างโมดูล Odoo 17 สำหรับจัดการคำขอด้านไอที (IT Request Suite) แยกออกเป็น 3 ฟอร์มอิสระ ไม่ใช้ form เดียวกัน และมีแดชบอร์ดรวมการทำงานของทีม IT

⸻

🧩 Module Information
	•	Module Name: buz_it_request
	•	Odoo Version: 17.0 (Community)
	•	Category: IT Management / Helpdesk / Purchase
	•	Author: Ball (MOGEN)
	•	Description: รวมระบบคำขอด้าน IT ทั้งหมดไว้ในโมดูลเดียว แต่แยกออกเป็น 3 ฟอร์ม คือ
	1.	IT Request – แจ้งซ่อม / ปัญหา
	2.	IT Access Request – ขอใช้งานระบบไอที
	3.	IT Procurement Request – ขอซื้ออุปกรณ์ไอที
	•	Dashboard: รวมสถานะทุกประเภทเป็นการ์ด + กราฟ สำหรับทีม IT

⸻

🧱 Structure

buz_it_request/
├── __init__.py
├── __manifest__.py
├── security/
│   ├── ir.model.access.csv
│   └── security.xml
├── data/
│   ├── sequence.xml
│   ├── mail_activity.xml
│   ├── dashboard_data.xml
│   └── sla_data.xml
├── models/
│   ├── it_ticket_issue.py
│   ├── it_request_access.py
│   ├── it_request_procurement.py
├── views/
│   ├── menu.xml
│   ├── it_ticket_issue_views.xml
│   ├── it_request_access_views.xml
│   ├── it_request_procurement_views.xml
│   ├── dashboard_views.xml
│   └── report_templates.xml
└── report/
    ├── report_issue.xml
    ├── report_access.xml
    └── report_procurement.xml


⸻

🧩 Model 1: it.ticket.issue – แจ้งซ่อม / ปัญหา

Fields
	•	name (sequence)
	•	requester_id (employee)
	•	department_id, location_id
	•	category_id (computer, printer, network, software, other)
	•	priority (Low/Normal/High/Urgent)
	•	issue_date, due_date, resolved_date
	•	description, attachment_ids
	•	assignee_id (IT staff)
	•	root_cause, resolution_note
	•	state: draft → triage → in_progress → waiting_user → done → cancel
	•	sla_status: on_track / risk / breached

Logic
	•	SLA คำนวณอัตโนมัติตาม priority + calendar
	•	ปิดงานต้องมี resolution_note
	•	Auto assign technician ตาม category
	•	แจ้งเตือน SLA ใกล้หมดอายุ / breach ผ่าน activity

⸻

🧩 Model 2: it.request.access – ขอใช้งานระบบไอที

Flow
	1.	User ส่งคำขอ (draft → to_manager_approve)
	2.	Manager อนุมัติ (→ manager_approved)
	3.	IT ดำเนินการ (→ to_it → it_in_progress → done)

Fields
	•	name (sequence)
	•	requester_id, employee_id
	•	request_type (Email, ERP, VPN, Wi-Fi, Shared Folder, etc.)
	•	system_detail, justification
	•	manager_id, approval_note
	•	it_operator_id, it_note
	•	checklist_ids (ตาม template)
	•	attachment_ids
	•	state: draft → to_manager_approve → manager_approved → to_it → done

Logic
	•	เมื่อ manager อนุมัติ → auto activity ส่งให้ IT
	•	Checklist template ต่อชนิดการขอ (เช่น Email, ERP, VPN)
	•	บันทึกสิทธิ์ที่มอบให้ (role, username)
	•	พิมพ์ฟอร์ม ISO พร้อมลายเซ็น

⸻

🧩 Model 3: it.request.procurement – ขอซื้ออุปกรณ์ไอที

Flow
	1.	User สร้างคำขอ (draft)
	2.	Manager Approve (→ manager_approved)
	3.	IT ตรวจสอบ / เปิด PR (→ it_reviewed → pr_created)
	4.	ติดตามสถานะ PR/PO → done

Fields
	•	name (sequence)
	•	requester_id, department_id
	•	justification
	•	line_ids (One2many): product, description, qty, uom, est_price
	•	manager_id, approval_note
	•	it_operator_id, it_spec_note
	•	purchase_request_id / purchase_order_id
	•	state: draft → to_manager_approve → manager_approved → to_it → it_reviewed → pr_created → done

Logic
	•	ปุ่ม Create PR: ตรวจสอบโมดูล purchase_request → ถ้ามีใช้ PR ถ้าไม่มีใช้ RFQ
	•	Smart button: ลิงก์เอกสาร PR/PO ที่สร้าง
	•	รายงาน ISO พิมพ์ฟอร์มคำขอซื้อ

⸻

📊 Dashboard (IT Overview)

KPI Cards
	•	Open Issues (ทั้งหมด/ตาม priority)
	•	Awaiting Manager Approval (Access/Procurement)
	•	Awaiting IT Action (ทุกประเภท)
	•	SLA Breached / At Risk
	•	PR Created / Waiting Vendor / Received

Charts
	•	Bar: จำนวนงาน IT ตามหมวด/สัปดาห์
	•	Pie: งานแยกตามประเภท (Issue/Access/Procurement)
	•	Line: SLA On-time vs Breach
	•	Table: รายการใกล้ครบกำหนด (due_date)

⸻

🔐 Security

Groups
	•	group_it_user: เจ้าหน้าที่ IT (ดู/แก้ไขงานทั้งหมด)
	•	group_it_manager: ผู้จัดการ IT (ตั้งค่า/รายงาน)
	•	group_it_requester: พนักงานทั่วไป (ดูเฉพาะที่สร้าง)
	•	group_it_manager_approver: หัวหน้าแผนก (อนุมัติ Access/Procurement)

Record Rules
	•	Requester: see own records only
	•	IT User: see all records
	•	Manager Approver: see requests in own department

⸻

⚙️ Configuration
	•	SLA Policy ต่อ Priority
	•	Category / Checklist Template ต่อประเภทคำขอ
	•	Working Calendar / วันหยุด IT
	•	Auto Assignment Rule ต่อ category
	•	Email alias: it@company.com → auto create Issue
	•	Integration: purchase_request, purchase, HR Onboarding

⸻

📑 Report Forms
	1.	แบบฟอร์มแจ้งซ่อม (IT Issue)
	2.	แบบฟอร์มขอใช้งานระบบ (IT Access)
	3.	แบบฟอร์มขอซื้ออุปกรณ์ (IT Procurement)

แต่ละแบบมี:
	•	หมายเลขเอกสาร (Sequence)
	•	ลายเซ็นผู้ขอ / ผู้อนุมัติ / ผู้ดำเนินการ
	•	วันที่ / หมายเหตุ / แนบไฟล์

⸻

🧮 KPI / Analytics
	•	MTTR (Mean Time To Repair)
	•	SLA On-time vs Breached
	•	งานที่รออนุมัติ (Access/Procurement)
	•	มูลค่า PR รวมตามแผนก/เดือน

⸻

🧠 Key Python Hooks

def _compute_sla_status(self):
    # คำนวณ SLA ตาม calendar / priority
    ...

def _action_auto_assign(self):
    # เลือก assignee อัตโนมัติจาก category
    ...

def _action_create_pr(self):
    # สร้าง PR หรือ RFQ อัตโนมัติ
    ...

def _prepare_checklist(self):
    # ดึง checklist จาก template สำหรับ Access Request
    ...


⸻

📦 Deliverables
	•	โมดูลพร้อม install ได้ (buz_it_request)
	•	มี security, dashboard, report, flow ครบ 3 โมเดล
	•	รองรับ multi-company, multi-user, record rules ครบ

⸻

🚀 Next Step (ให้มะนาวสร้างโค้ดได้ทันที)

Prompt:

สร้างโมดูล Odoo 17 ชื่อ buz_it_request ตามสเปคในไฟล์นี้ พร้อม 3 โมเดล (Issue, Access, Procurement) และ dashboard รวม ให้ครบพร้อมติดตั้งได้