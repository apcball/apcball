Goals
	•	โมดูลชื่อ buz_it_ticket ติดตั้งแล้วใช้งานได้ทันที
	•	ใช้ โมเดลเดียว it.ticket แยก flow ด้วย category = issue | access | purchase
	•	ทำ 3 flow ครบ (ไม่เน้นเฉพาะ PO):
	•	Issue/Repair: รับแจ้ง → ทำงาน → ขอข้อมูลเพิ่ม (ถ้ามี) → แก้เสร็จ → ปิด
	•	Access: ผู้ขอ → Manager อนุมัติ → IT ดำเนินการสร้างสิทธิ์/บัญชี → ปิด
	•	Purchase: ผู้ขอ → Manager อนุมัติ → IT ตรวจสอบ → สร้าง PO → รับของ → ปิด
	•	สร้างรายงาน QWeb สำหรับ ISO ทั้ง 3 หมวด + Summary
	•	มี Dashboard กราฟ/พิวอต/บอร์ด แยกตามหมวด
	•	มี Demo Data (ถ้า demo=True) และ Uninstall ได้สะอาด

Dependencies

hr, mail, uom, purchase, web (+ stock เป็นทางเลือกถ้ารับเข้าอุปกรณ์)

Security & Groups
	•	group_it_requester (พนักงานผู้ขอ)
	•	group_it_user (เจ้าหน้าที่ IT)
	•	group_it_manager (หัวหน้า IT)
	•	group_it_approver (ผู้อนุมัติสายงาน/HR/Finance—เผื่อขยาย)
	•	group_it_iso_auditor (อ่าน+พิมพ์ ISO)

Record Rules (สำคัญ):
	•	Requester เห็นเฉพาะ ticket ของตน [('employee_id.user_id', '=', user.id)]
	•	IT/Manager เห็นในบริษัทตน, หรือทุกใบตามกลุ่ม

Data Model

it.ticket (core)

ฟิลด์หลัก:
	•	name (sequence; prefix ตาม category: ISS/…, ACS/…, PRC/…)
	•	category (selection: issue, access, purchase, required)
	•	state (selection; แตกต่างตามหมวด—ดูด้านล่าง)
	•	employee_id (m2o hr.employee, required)
	•	manager_id (m2o hr.employee, compute จาก employee_id.parent_id, store=True)
	•	it_responsible_id (m2o res.users)
	•	priority (Low/Normal/High/Urgent)
	•	company_id, department_id, user_id (ผู้สร้าง)
	•	description, attachment_ids
	•	SLA: sla_policy_id, deadline_sla, responded_at, resolved_at, ttr_respond, ttr_resolve, sla_breached (bool)
	•	Access: access_template_id, access_line_ids (รายละเอียดสิทธิ์)
	•	Purchase: purchase_line_ids (o2m), purchase_id (m2o purchase.order)
	•	ISO: iso_doc_code, revision, printed_count, printed_by, printed_at
	•	Inherit: mail.thread, mail.activity.mixin

it.ticket.line

ใช้ร่วมหมวด Access และ Purchase:
	•	ticket_id (m2o, cascade)
	•	name (Char, required)
	•	product_id (m2o product.product, optional สำหรับ purchase)
	•	uom_id (m2o uom.uom), quantity (Float, default=1.0)
	•	estimated_cost (Float; purchase)
	•	access_type (selection: email/erp/vpn/drive/shared-folder/etc.)
	•	access_payload (Text/JSON—เช่น กลุ่ม, role, module)

it.sla.policy (สั้น ๆ)
	•	เงื่อนไข: category, priority, subtype (optional)
	•	ค่า: response_time_hours, resolve_time_hours

it.access.template (optional, ชุดสิทธิ์สำเร็จรูป)
	•	name, department, lines (ชนิดสิทธิ์/กลุ่ม/role)

State Machines (3 หมวด)

1) Issue/Repair (แจ้งปัญหา–แจ้งซ่อม)

draft → submitted → in_progress → pending_info → resolved → closed (หรือ cancel)
	•	Submit: สร้าง activity ให้ IT, ตั้ง SLA
	•	In Progress: IT เริ่มงาน
	•	Pending Info: ขอข้อมูลเพิ่ม (แจ้ง requester)
	•	Resolved: แก้เสร็จ, บันทึกผล
	•	Closed: ผู้ขอคอนเฟิร์มหรือ auto-close ภายใน X วัน

2) Access (ขอใช้งานระบบ)

draft → submitted → waiting_manager → approved → implementing → closed (หรือ rejected/cancel)
	•	Submit: ส่งให้ Manager อนุมัติ (ดึง manager_id อัตโนมัติ)
	•	Approved: Manager อนุมัติครบ → ไป Implementing
	•	Implementing: IT ดำเนินการตาม access_line_ids (สร้าง email/เพิ่ม ERP group ฯลฯ)
	•	Closed: สำเร็จ + แจ้งผู้ขอ

3) Purchase (ขอซื้ออุปกรณ์)

draft → submitted → waiting_manager → waiting_it → po_created → received → closed (หรือ rejected/cancel)
	•	Submit: ส่ง Manager
	•	Waiting IT: Manager อนุมัติแล้วส่งต่อ IT ตรวจสอบ
	•	Create PO: IT กดสร้าง PO จาก purchase_line_ids
	•	Received: รับของ/ส่งมอบ (เชื่อม stock picking ถ้ามี)
	•	Closed: ปิดงาน

Buttons & Permissions (ตัวอย่างหลัก)
	•	Issue
	•	Submit (requester), Start Work/Need Info/Resolve/Close (IT/Manager)
	•	Access
	•	Submit (requester)
	•	Manager Approve/Reject (เฉพาะ manager)
	•	Start Implement / Mark Done (IT)
	•	Purchase
	•	Submit (requester)
	•	Manager Approve/Reject (manager)
	•	Create PO (IT), Mark Received/Close (IT/Manager)

Business Logic ที่ต้องใส่
	•	คำนวณ SLA deadline เมื่อ Submit ตาม sla_policy_id
	•	บันทึก responded_at เมื่อ state เปลี่ยนจาก submitted ครั้งแรก
	•	บันทึก resolved_at เมื่อเข้าสู่ resolved/closed (หมวด issue) หรือ closed (access/purchase)
	•	ตั้ง sla_breached ถ้าเลย deadline_sla
	•	ทุกการเปลี่ยน state ให้ message_post และ mail.activity ไปยังผู้เกี่ยวข้อง
	•	สร้าง purchase.order จาก purchase_line_ids: map name/product_id/qty/uom/price_unit/date_planned + origin=ticket.name, link กลับ purchase_id

Views & Menu
	•	เมนูหลัก: IT Tickets
	•	Submenu: Tickets (list/kanban/graph/pivot), Dashboard, Reports, Configuration (SLA/Access Templates)
	•	Search filters: category/state/priority/department/IT responsible/SLA breach
	•	Kanban: แยกคอลัมน์ตาม state พร้อม badge SLA
	•	Smart buttons: PO, Activities, Print Count

Reports (QWeb, ISO)
	•	Issue Report (ISO): ข้อมูลปัญหา, ขั้นตอนแก้ไข, ผู้ดำเนินการ, ลายเซ็น ตรวจทาน
	•	Access Request Form (ISO): รายละเอียดสิทธิ์, ผู้อนุมัติ, ลายเซ็น
	•	IT Purchase Request (ISO): รายการจะซื้อ + ผู้อนุมัติ + เลข PO
	•	Ticket Summary (Batch): เลือกช่วงวันที่/หมวด แสดงตารางสรุป
	•	ก่อนพิมพ์ทุกครั้งให้บันทึก printed_by, printed_at, เพิ่ม printed_count

Dashboard (Graph/Pivot/Board)
	•	การ์ดนับ: Issue Open/Overdue/SLA Breach, Access Waiting Manager/Implementing, Purchase Waiting Manager/Waiting IT/PO Created
	•	กราฟ: จำนวน ticket ต่อแผนก/ประเภท/ผู้รับผิดชอบ (7/30 วัน), Avg TTR Respond/Resolve
	•	Pivot: สรุป cost (purchase) ต่อแผนก/vendor, จำนวน access ต่อ template

File Structure (ให้โค้ดเจนสร้าง)
buz_it_ticket/
├─ __manifest__.py
├─ __init__.py
├─ security/
│  ├─ ir.model.access.csv
│  └─ security.xml
├─ data/
│  ├─ sequence.xml
│  ├─ mail_templates.xml
│  ├─ sla_data.xml
│  ├─ access_templates.xml
│  └─ demo_data.xml
├─ models/
│  ├─ it_ticket.py
│  ├─ it_ticket_line.py
│  ├─ it_sla_policy.py
│  └─ it_access_template.py
├─ views/
│  ├─ it_ticket_views.xml
│  ├─ it_ticket_actions.xml
│  ├─ it_ticket_menu.xml
│  ├─ it_dashboard_views.xml
│  └─ it_config_views.xml
└─ report/
   ├─ it_issue_report.xml
   ├─ it_access_request_report.xml
   ├─ it_purchase_request_report.xml
   └─ it_ticket_summary_report.xml
 Acceptance Criteria (สำคัญ)
	1.	Issue: สร้าง–Submit–In Progress–Pending Info–Resolved–Closed ได้ครบ, SLA คำนวณและ breach ถูกต้อง
	2.	Access: Submit แล้วส่งถึง Manager, อนุมัติแล้ว IT ทำ Implement, ปิดงานแล้วแจ้งผู้ขอ
	3.	Purchase: Submit → Manager Approve → IT Create PO จาก lines → link PO กลับ ticket → Mark Received/Close
	4.	ISO Print: พิมพ์ได้ทั้ง 3 แบบ, printed_count/by/at ถูกบันทึก
	5.	Dashboard: มีกราฟ/พิวอต/ตัวนับตามหมวด ใช้งานได้
	6.	Security: Requester เห็นเฉพาะของตน, ปุ่มแสดงตาม state+groups, ไม่เกิด access error
	7.	Demo: โหลด demo ผ่าน (พนักงาน/ผู้จัดการ/IT, ตัวอย่าง issue/access/purchase หลายสถานะ)
	8.	Uninstall: ไม่ทิ้ง orphan (m2o/o2m cascade พร้อม)

Notes ให้โค้ดเจน
	•	ใช้ _() ครอบข้อความแปลได้
	•	ใช้ @api.depends + store=True กับ manager_id/metric ที่จำเป็น
	•	ใช้ mail.activity แจ้งเตือนทุกจุดเปลี่ยน state สำคัญ
	•	รองรับ multi-company (company_id)
	•	ใส่ domain vendor/supplier ใน purchase ถ้าทำ wizard เลือก vendor
	•	แยก sequence ตาม category (ISS/ACS/PRC)

Optional Extensions (ใส่เป็น placeholder/comment)
	•	Portal สำหรับพนักงานติดตามงาน
	•	Auto-close issue หลัง 3–7 วันถ้า requester ไม่ตอบ
	•	เชื่อม stock picking & asset สร้างทรัพย์สินอัตโนมัติ
	•	Access automation (สคริปต์ต่อ API/LDAP/SSO) — mock method ไว้ก่อน

