# Helpdesk Plan

## โครงสร้างเมนู

```text
IT Management
└── Helpdesk
    ├── My Tickets
    ├── Tickets
    └── Configuration
        ├── Categories
        ├── Teams
        └── Stages
```

## ขอบเขต Phase 1

- ใช้ dependency เฉพาะ `base`
- สร้าง root menu `IT Management` และเมนู `Helpdesk` ภายในโมดูลเอง
- มีเฉพาะ `My Tickets`, `Tickets` และ `Configuration`
- ยังไม่รวม Dashboard
- ยังไม่รวม My Assigned Tickets
- ยังไม่รวม Knowledge Base
- ยังไม่รวม Reporting
- ยังไม่รวม SLA Policies
- ใช้ XML ID, actions, models และ security groups ภายในโมดูลเท่านั้น
- ไม่อ้างอิงเมนูหรือ model จากโมดูลอื่น

## ขอบเขต Phase 2: บังคับใช้ Workflow และความปลอดภัยของ Ticket

เป้าหมายของ Phase 2 คือทำให้ workflow และสิทธิ์ของ Ticket ถูกบังคับใช้ที่ฝั่ง
Server ไม่ขึ้นกับการซ่อนปุ่มหรือข้อจำกัดใน View เท่านั้น โดยต้องรักษา role,
สถานะ และข้อมูลข้ามบริษัทให้สอดคล้องกันเมื่อเรียกผ่าน UI, RPC หรือ API

### Phase 2.1: กำหนด Workflow และ Transition Rule

- กำหนด Technical Stage Code ที่คงที่สำหรับ `draft`, `new`, `in_progress`,
  `pending_user`, `resolved`, `closed` และ `cancelled`
- กำหนด transition ที่อนุญาตอย่างชัดเจน เช่น
  `Draft → New → In Progress → Resolved → Closed`
- รองรับ `In Progress ↔ Pending User` ตามกติกาที่กำหนด
- กำหนดเงื่อนไข Reopen และ Cancel แยกต่างหาก พร้อมระบุ role ที่ทำได้
- ห้ามข้ามสถานะหรือย้อนสถานะโดยตรง เว้นแต่เป็น transition ที่ประกาศไว้
- ห้ามพึ่งพา `sequence` เพื่อระบุ Draft; Stage เริ่มต้นต้องอ้างอิง Stage ที่มี
  code เป็น `draft` โดยตรง
- ตรวจสอบความถูกต้องของ Stage Code ไม่ให้ซ้ำ และกำหนดพฤติกรรมเมื่อข้อมูล Stage
  ไม่ครบหรือถูกปิดใช้งาน

ไฟล์หลักที่เกี่ยวข้อง:

- `models/helpdesk_ticket.py`
- `models/helpdesk_stage.py`
- `data/helpdesk_data.xml`
- `views/helpdesk_ticket_views.xml`

เกณฑ์ตรวจรับ: การเปลี่ยน Stage ที่ไม่อยู่ใน transition map ต้องถูกปฏิเสธจาก
Server แม้เรียกด้วย RPC โดยตรง และ Ticket ที่สร้างใหม่ต้องเริ่มที่ Draft เสมอ

### Phase 2.2: บังคับ Role และสถานะใน Server Methods

- ให้ `action_create_ticket` ตรวจสอบ role ของผู้เรียกและสถานะต้นทางก่อนทำงาน
- ให้ `action_receive_ticket` ตรวจสอบ role, สถานะต้นทาง, Team และ Assigned To
  ตามกติกาเดียวกับ workflow
- ตรวจสอบสิทธิ์ในทุก method ที่เปลี่ยนสถานะ ไม่ถือว่าการซ่อนปุ่มใน View เป็น
  การควบคุมความปลอดภัย
- กำหนดให้ Requester สร้าง Ticket ได้จาก Draft แต่ไม่สามารถเรียก RPC เพื่อ
  ข้ามไปสถานะอื่น หรือแก้ไขข้อมูลที่เป็นของ Agent/Manager ได้
- กำหนดสิทธิ์ Agent และ Manager ให้ชัดเจน และใช้สิทธิ์ Manager ที่ implied
  Agent โดยไม่ตรวจซ้ำหลายตำแหน่งโดยไม่จำเป็น
- ป้องกัน Requester เปลี่ยนเจ้าของ Ticket และกำหนดขอบเขตการแก้ไขหลัง Confirm
- ตรวจสอบกรณีผู้ใช้ไม่มี role, role ไม่ตรงกับสถานะ หรือข้อมูลที่เกี่ยวข้องไม่ครบ
  แล้วคืน UserError/AccessError ที่เหมาะสม

ไฟล์หลักที่เกี่ยวข้อง:

- `models/helpdesk_ticket.py`
- `security/security.xml`
- `security/ir.model.access.csv`
- `security/helpdesk_extra_security.xml`

เกณฑ์ตรวจรับ: เรียก method ผ่าน RPC โดยปลอมเป็น Requester/Agent/Manager แล้วได้
ผลตาม role และสถานะที่กำหนด โดยการเรียกที่ไม่ถูกต้องต้องไม่เปลี่ยนข้อมูลได้

### Phase 2.3: ปรับค่าเริ่มต้นและการควบคุมจาก UI

- ใน Draft ให้ Requester กรอกข้อมูลคำขอที่จำเป็นได้ แต่ไม่เลือกหรือแก้ไข
  `Requester`, `Team` และ `Assigned To` หากกติกากำหนดให้ระบบหรือ Agent เป็นผู้กำหนด
- ตรวจสอบเงื่อนไขการแสดงปุ่ม `Receive Ticket` ให้ไม่หายไปเพราะมีผู้รับถูกกำหนด
  ก่อนส่งคำขอ
- แยก field ที่ผู้สร้างกรอกได้ออกจาก field ที่ Agent/Manager ควบคุม และทำให้
  readonly/invisible สอดคล้องกับ role และสถานะ
- ปิดการบันทึกอัตโนมัติของ Priority ใน Form, List และ Kanban ตามพฤติกรรมที่ต้องการ
  หรือเปลี่ยนเป็นการควบคุมด้วย Server หาก widget มาตรฐานยังบันทึกทันที
- ตรวจสอบปุ่ม, statusbar, readonly และ domain ใน Form/List/Kanban ให้ใช้กติกา
  เดียวกัน ไม่ให้ UI แต่ละแบบเปิดช่องทางเปลี่ยนข้อมูลไม่เท่ากัน

ไฟล์หลักที่เกี่ยวข้อง:

- `views/helpdesk_ticket_views.xml`
- `static/src/js/` และไฟล์ XML ของ component ที่เกี่ยวข้อง หากจำเป็น

เกณฑ์ตรวจรับ: พฤติกรรมของ Form, List และ Kanban ต้องไม่ทำให้ Priority หรือ
สถานะถูกบันทึกโดยไม่ผ่านกติกาที่กำหนด และปุ่ม Receive Ticket ต้องแสดงตามข้อมูล
และ role ที่ถูกต้อง

### Phase 2.4: Multi-company และ Notification/Activity

- เพิ่ม `company_id` ให้ Ticket และ model ที่เกี่ยวข้องตามขอบเขตการใช้งาน
- กำหนด default company และตรวจ `check_company=True` สำหรับ relation ที่ข้าม
  ไปยัง Company-dependent model
- เพิ่ม Record Rule ให้ผู้ใช้เห็นและแก้ไขได้เฉพาะข้อมูลของบริษัทที่มีสิทธิ์
  พร้อมทดสอบกรณีเปลี่ยน Current Company
- ตรวจ ACL และ Record Rule ของ Ticket, Stage, Category, Priority, Tag, Team
  และข้อมูลที่ Ticket อ้างอิงให้ไม่ขัดกัน
- เพิ่ม notification หรือ activity เมื่อ Create Ticket โดยระบุผู้รับตาม Team,
  Agent หรือ Manager ที่กำหนดไว้
- ป้องกันการสร้าง notification/activity ซ้ำเมื่อ method ถูกเรียกซ้ำหรือ retry

ไฟล์หลักที่เกี่ยวข้อง:

- `models/` ของ Ticket และ model ที่เกี่ยวข้อง
- `security/security.xml`
- `security/helpdesk_extra_security.xml`
- `security/ir.model.access.csv`
- `data/` สำหรับ activity type หรือ template หากจำเป็น

เกณฑ์ตรวจรับ: ผู้ใช้บริษัทหนึ่งต้องไม่อ่านหรือแก้ไข Ticket/ข้อมูลอ้างอิงของอีก
บริษัทโดยไม่ได้รับสิทธิ์ และการสร้าง Ticket ต้องสร้าง notification/activity ตาม
กติกาโดยไม่เกิดรายการซ้ำ

### Phase 2.5: Automated Tests, Static Checks และ UAT

- เพิ่ม automated tests สำหรับการสร้าง Ticket, ค่าเริ่มต้น Draft และ transition
  ที่อนุญาต/ไม่อนุญาต
- เพิ่ม tests แยกตาม Requester, Agent และ Manager รวมถึงการเรียกผ่าน method/RPC
- เพิ่ม tests สำหรับ `action_create_ticket` และ `action_receive_ticket` ทั้ง role
  และสถานะต้นทาง
- เพิ่ม tests สำหรับการแก้ไข Team, Assigned To, Requester และ Priority ในแต่ละ
  สถานะและแต่ละ View ที่เกี่ยวข้องเท่าที่ Odoo test framework รองรับ
- เพิ่ม tests Multi-company, ACL, Record Rule และ notification/activity
- ตรวจ XML parse, manifest files, XML ID ซ้ำ, JavaScript และ `git diff --check`
- จัดทำ UAT checklist สำหรับ workflow หลัก, invalid transition, role matrix,
  multi-company และการแจ้งเตือน
- แยกหลักฐานเป็น Static, Runtime/Automated Test, Deploy DEV และ Rendered UI/PDF;
  ห้ามสรุปผล Runtime หรือ Deploy DEV จาก Static Check เพียงอย่างเดียว

ไฟล์หลักที่เกี่ยวข้อง:

- `tests/__init__.py`
- `tests/test_helpdesk.py` หรือไฟล์ test ที่แยกตามความเหมาะสม
- `PHASE_2_UAT_SCENARIOS.md` หากต้องจัดทำเอกสาร UAT แยก

เกณฑ์ตรวจรับ: automated tests ต้องครอบคลุม security boundary และ transition
สำคัญทั้งหมด, static checks ต้องผ่าน และรายงานผลต้องระบุชัดเจนว่าส่วนใดผ่านจาก
การตรวจแบบใดหรือยังไม่ได้ยืนยันด้วย Runtime/Deploy DEV