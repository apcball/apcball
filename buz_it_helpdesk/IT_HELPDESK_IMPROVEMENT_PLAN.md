# แผนปรับปรุง IT Helpdesk ให้พร้อมใช้งานจริง

เอกสารนี้เป็นแผนงานสำหรับให้ Codex ดำเนินการปรับปรุงโมดูล `buz_it_helpdesk` แบบเป็นระยะ
ห้ามดำเนินการทุกระยะในครั้งเดียว ให้ทำเฉพาะระยะที่ผู้ใช้ระบุ แล้วหยุดรอคำสั่งถัดไป

## กติกาการทำงาน

1. ก่อนเริ่มแต่ละระยะ ให้ตรวจสอบสถานะ Git และอ่านไฟล์ที่เกี่ยวข้องก่อนแก้ไข
2. แก้เฉพาะขอบเขตของระยะนั้น ห้ามทำงานข้ามระยะโดยไม่ได้รับอนุญาต
3. ใช้ `apply_patch` ในการแก้ไขไฟล์
4. ห้ามทดสอบกับฐานข้อมูล Production หรือฐานข้อมูล DEV ที่มีข้อมูลจริง
5. ใช้ฐานข้อมูลทดสอบแยกผ่าน `docker-compose.test.yml` เมื่อสภาพแวดล้อมพร้อม
6. หลังแก้ไข ให้รันการตรวจสอบที่เหมาะสมกับระยะนั้น
7. สรุปไฟล์ที่แก้ไข, ผลการทดสอบ, ปัญหาที่พบ และงานที่ยังไม่ทำ
8. เมื่อจบแต่ละระยะ ให้หยุดและรอคำสั่งจากผู้ใช้
9. ทุก Bug ที่แก้ต้องมี Regression Test หากสามารถทดสอบด้วย Odoo Test Runner ได้
10. ห้ามเปลี่ยน Schema, Security, Workflow หรือข้อมูลเริ่มต้นนอกขอบเขต Phase ที่กำลังทำ
11. ห้ามถือว่า Phase ผ่าน หากยังไม่ได้ตรวจ Upgrade จากข้อมูลเดิมที่เกี่ยวข้องกับ Phase นั้น
12. หากพบ Blocker นอกขอบเขต ให้บันทึกไว้ในรายงานและหยุดรอคำสั่ง ห้ามขยายงานเอง

## Definition of Done กลาง

ทุก Phase ต้องผ่านเงื่อนไขต่อไปนี้ก่อนเริ่ม Phase ถัดไป:

- ขอบเขตและ Acceptance Criteria ของ Phase ผ่านครบ
- ไม่มี Critical หรือ High Severity Issue ที่เกิดจากการแก้ไขค้างอยู่
- Tests ของ Phase ผ่านบนฐานข้อมูลทดสอบแยก
- ติดตั้งใหม่และ Upgrade Module ได้สำหรับส่วนที่แก้
- Security Tests ผ่านสำหรับ Requester, Agent, Manager และ Multi-company
- ไม่มีข้อมูลลับปรากฏใน Log, Chatter, Notification, Search หรือ Report
- มีรายงานไฟล์ที่แก้, Migration Impact, ผลทดสอบ และ Known Issues
- ผู้ใช้ตรวจรับผลของ Phase ก่อนสั่ง Phase ถัดไป

## รูปแบบรายงานเมื่อจบแต่ละ Phase

```text
Phase:
สถานะ: Passed / Passed with known issues / Blocked
ไฟล์ที่แก้:
Migration impact:
Tests ที่รัน:
ผลการทดสอบ:
Security checks:
Known issues:
Rollback:
งานที่ยังไม่ทำ:
```

## ตารางสถานะการดำเนินงาน

ให้ปรับเฉพาะช่องสถานะเมื่อผู้ใช้ตรวจรับแล้ว:

| ระยะ | สถานะเริ่มต้น | ผู้ตรวจรับ |
|---|---|---|
| 0 Baseline | Not Started | ผู้ใช้ |
| 1 Ticket Intake | Not Started | ผู้ใช้ |
| 2 Multi-company & Security | Not Started | ผู้ใช้ |
| 3 Helpdesk Workflow | Not Started | ผู้ใช้ |
| 4 SLA, Notification & Portal | Not Started | ผู้ใช้ |
| 5A Asset Architecture & Migration | Not Started | ผู้ใช้ |
| 5B Asset Master & Forms | Not Started | ผู้ใช้ |
| 5C Assignment, Repair & History | Not Started | ผู้ใช้ |
| 5D Renewal & Notification | Not Started | ผู้ใช้ |
| 6 Unified Dashboard | Not Started | ผู้ใช้ |
| 7 Regression, Security Review & UAT | Not Started | ผู้ใช้ |
| 8 UAT Procedure Design: User & IT | Not Started | ผู้ใช้และ IT |

## นโยบายช่องทางการแจ้งเตือน

ให้ใช้ระบบแจ้งเตือนกลางร่วมกันระหว่าง Helpdesk และ IT Asset แต่กำหนดช่องทางตามประเภทงาน

### IT Asset

- ใช้ Email เป็นช่องทางภายนอกหลักสำหรับ Software License ที่ใกล้หมดอายุ
- ใช้ Odoo Activity/Chatter ควบคู่เพื่อเก็บหลักฐานและมอบหมายงาน
- รองรับการแจ้งเตือน 90/60/30 วัน และแจ้งเตือนเมื่อหมดอายุ

### Helpdesk

- ระยะแรก **ยังไม่ส่ง Email สำหรับการแจ้งเตือน Helpdesk**
- ใช้ Odoo Activity สำหรับมอบหมายงานและแจ้งผู้รับผิดชอบ
- ใช้ Odoo Chatter สำหรับเก็บประวัติการเปลี่ยนแปลงและการสื่อสาร
- ใช้ Dashboard และหน้ารายการ Ticket สำหรับติดตาม SLA และงานค้าง
- ออกแบบให้สามารถเพิ่ม Email, LINE หรือ Microsoft Teams ในอนาคตได้ โดยไม่ต้องเปลี่ยน Workflow หลัก

### หลักการออกแบบร่วม

- แยก Event ของ Helpdesk และ IT Asset ออกจาก Channel ที่ใช้ส่ง
- ป้องกันการแจ้งเตือนซ้ำด้วย Notification Log หรือ Dedupe Key
- บันทึกผู้รับ, เวลา, ช่องทาง และผลการส่งทุกครั้ง
- ห้ามส่ง License Key ในข้อความแจ้งเตือน
- Incoming Email สำหรับสร้าง Ticket และ Outbound Email สำหรับแจ้งเตือนต้องเป็นคนละ Configuration
- การเพิ่ม Channel ใหม่ในอนาคตต้องไม่แก้ Workflow หลักของ Helpdesk หรือ IT Asset

## ระยะที่ 0: Baseline และตรวจสอบสภาพแวดล้อม

### เป้าหมาย

เก็บสถานะเริ่มต้นก่อนแก้ไข เพื่อให้เปรียบเทียบผลได้และไม่กระทบงานเดิม

### งาน

- ตรวจสอบ `git status`
- ตรวจสอบโครงสร้างโมดูลและ `__manifest__.py`
- ตรวจสอบว่า Python, Odoo และ Docker test environment ใช้งานได้หรือไม่
- ตรวจสอบรายการ Test ที่มีอยู่ใน `tests/`
- ตรวจสอบ XML และ Python เบื้องต้นโดยไม่สร้างไฟล์ต้องห้าม
- ตรวจสอบว่า `docker-compose.test.yml` ใช้ `buz_it_helpdesk` และฐานข้อมูล `MOG_TEST`
- เก็บจำนวน Ticket และ Asset แยกตาม Company, Stage และ Asset Type ก่อน Migration
- ตรวจสอบว่ามีข้อมูล `email` หรือ `system_account` เดิมในฐานข้อมูลหรือไม่
- ตรวจสอบ Mail Alias, Outgoing Mail Server, Cron และ Mail Queue โดยไม่ส่งข้อความจริง
- บันทึก Decision Log สำหรับ User Type ของ Requester ว่าเป็น Internal User หรือ Portal User
- บันทึก Baseline ของ Access Rights, Record Rules และ Group Membership
- ระบุคำสั่ง Install, Upgrade, Test และ Rollback ที่จะใช้ใน Phase ต่อไป
- ห้ามแก้ไขโค้ดในระยะนี้

### เกณฑ์ผ่าน

- มีรายงานสถานะเริ่มต้น
- ระบุคำสั่งทดสอบที่ใช้งานได้และใช้งานไม่ได้
- มีรายงานจำนวนข้อมูลเดิมและ Migration Risk
- มี Role/Security Baseline
- มีผลตรวจว่า Test Environment ไม่เชื่อมต่อ DEV หรือ Production
- ไม่มีไฟล์ถูกแก้ไข

---

## ระยะที่ 1: แก้ Blocker ของการรับ Ticket

### เป้าหมาย

ทำให้การสร้าง Ticket ผ่าน Backend, Portal และ Email ทำงานได้อย่างถูกต้อง

### ไฟล์หลัก

- `models/helpdesk_ticket.py`
- `controllers/portal.py`
- `data/helpdesk_data.xml`
- `tests/test_helpdesk.py`
- `tests/test_helpdesk_ticket.py`

### งาน

- กำหนด Default Category สำหรับ Ticket ที่มาจาก Email
- ตรวจสอบ Default Priority และ Default Team
- ตรวจสอบการทำงานของ `message_new()` และ Email Alias
- ตรวจสอบค่า `category_id` และ `priority_id` จาก Portal
- ป้องกันค่า ID ที่ไม่ถูกต้องหรืออยู่นอกบริษัท
- เพิ่ม Test สำหรับ Email และ Portal input validation

### ข้อจำกัด

- ยังไม่เปลี่ยนโครงสร้าง Workflow
- ยังไม่เพิ่มประวัติ IT Asset
- ยังไม่ปรับปรุง Dashboard นอกเหนือจากสิ่งที่จำเป็นต่อการทดสอบ

### เกณฑ์ผ่าน

- สร้าง Ticket จาก Backend ได้
- สร้าง Ticket จาก Portal ได้
- Email ใหม่สร้าง Ticket ได้โดยไม่เกิด Required Field Error
- Email Reply ถูกผูกกับ Ticket เดิมได้
- ค่าที่มาจาก Portal ไม่สามารถข้าม Company ได้
- Tests ของระยะนี้ผ่าน

---

## ระยะที่ 2: ปรับปรุง Multi-company และข้อมูลเริ่มต้น

### เป้าหมาย

ให้บริษัทเดียวหรือหลายบริษัทสามารถใช้งาน Helpdesk ได้โดยไม่เห็นข้อมูลข้ามบริษัท

### ไฟล์หลัก

- `data/helpdesk_data.xml`
- `data/sequence.xml`
- `security/security.xml`
- `security/helpdesk_extra_security.xml`
- `security/ir.model.access.csv`
- Models ของ Stage, Category, Priority, SLA และ Team

### งาน

- กำหนดแนวทางข้อมูลว่าเป็น Global หรือแยกตาม Company
- ทำให้ Stage, Category, Priority, SLA และ Team มีข้อมูลพร้อมใช้ทุก Company
- ตรวจสอบ Default Stage, Default Priority และ Default Team
- ตรวจสอบ `_check_company_auto` และ `check_company=True`
- กำหนด Role Matrix สำหรับ Requester, Agent และ Manager
- ให้ Manager สืบทอดสิทธิ์ Agent หรือปรับทุก Workflow Method ให้รองรับ Manager อย่างสอดคล้อง
- ตรวจ ACL และ Record Rule ของ Ticket, Stage, Category, Priority, Tag, SLA, Team และ Report สำหรับทุกกลุ่ม
- ตรวจว่า Agent และ Manager ไม่เห็นข้อมูลต่าง Company แม้เข้าผ่าน RPC/API
- แยกสิทธิ์ IT Asset User, IT Asset Manager และสิทธิ์ดู License Key ก่อนเริ่ม Phase 5
- เพิ่ม Test สำหรับ User ที่อยู่คนละ Company

### เกณฑ์ผ่าน

- ผู้ใช้ Company A ไม่เห็น Ticket ของ Company B
- Ticket ไม่สามารถอ้างอิง Category, Priority, Team หรือ SLA ต่าง Company
- ทุก Company มีค่าเริ่มต้นที่จำเป็น
- Manager ที่มีเฉพาะกลุ่ม Manager ใช้ Workflow ที่ได้รับอนุญาตได้ครบ
- ACL และ Record Rule ผ่าน Role Matrix ทุก Model
- ติดตั้งใหม่และ Upgrade ได้โดยไม่เกิด Data Error

---

## ระยะที่ 3: ทำให้ Ticket Workflow ปลอดภัย

### เป้าหมาย

ป้องกันการข้ามขั้นตอนผ่าน UI, RPC หรือ API และทำให้สถานะมีความหมายคงที่

### ไฟล์หลัก

- `models/helpdesk_ticket.py`
- `models/helpdesk_stage.py`
- `models/helpdesk_dashboard.py`
- `views/helpdesk_views.xml`
- `data/helpdesk_data.xml`
- `tests/test_helpdesk.py`

### งาน

- บังคับ Ticket ใหม่ให้อยู่ใน Draft หรือ New ที่ถูกต้อง
- บังคับ Transition ตาม Workflow ที่กำหนด
- ป้องกันการเปลี่ยนจาก New ไป Closed หรือ Cancelled โดยตรง
- เพิ่ม Technical Stage Code แทนการพึ่งพา Sequence Number
- ตรวจสอบการ Reopen และการปิด Ticket
- เพิ่ม Action Cancel และกำหนดผู้ที่มีสิทธิ์ Cancel
- กำหนดว่า Resolved จะถูกปิดโดย Agent, Requester ยืนยัน หรือ Auto-close หลังจำนวนวันที่กำหนด
- เมื่อ Reopen ให้กำหนดการจัดการ `resolved_at`, SLA Deadline และ Overdue Notification รอบเดิม
- การเปลี่ยน Category/Priority ต้องบันทึกประวัติและห้าม Reset SLA โดยไม่มีเหตุผล
- Internal Note ต้องไม่นับเป็น First Response
- Activity ต้อง Clear เมื่อ Acknowledge/Assign ตามกติกา ไม่ใช่เพียงเปิด Ticket
- ป้องกัน Requester เปลี่ยนเจ้าของ Ticket
- ตรวจสอบสิทธิ์การแก้ไข Ticket หลัง Confirm

### Workflow ที่ต้องรองรับ

```text
Draft → New
New → In Progress
In Progress ↔ Pending User
In Progress → Resolved
Resolved → Closed
Draft/New/In Progress/Pending User → Cancelled ตามสิทธิ์ที่กำหนด
Closed/Cancelled → In Progress
```

### เกณฑ์ผ่าน

- Workflow ทำงานเหมือนกันทั้ง UI และ API
- การเปลี่ยน Sequence ของ Stage ไม่ทำให้สถานะผิด
- Requester แก้ Ticket หลัง Confirm ไม่ได้
- Closed Ticket ปิดซ้ำหรือแก้สถานะผิดไม่ได้
- Cancel, Reopen และ SLA State ทำงานถูกต้องทั้ง UI และ API
- Internal Note ไม่เปลี่ยน First Response Metric
- Activity ไม่ถูกลบเพียงเพราะเปิด Ticket
- Tests ครบทุก Transition และกรณีต้องห้าม

---

## ระยะที่ 4: ปรับปรุง SLA, Notification และ Portal

### เป้าหมาย

ให้การติดตาม SLA และการสื่อสารกับผู้แจ้งมีความถูกต้องและไม่แจ้งซ้ำ

### งาน

- ตรวจสอบการคำนวณ Response SLA
- ตรวจสอบ Resolution SLA
- ตรวจสอบการหยุดเวลาใน Pending User
- ตรวจสอบการกลับมานับเวลาเมื่อ Resume
- ตรวจสอบ Cron แจ้งเตือน SLA Overdue
- ป้องกัน Notification ซ้ำ
- ตรวจสอบ Chatter, Followers และ Activities
- บังคับนโยบายว่า Helpdesk ไม่สร้าง Outbound Email ในระยะนี้
- เพิ่ม Test ว่า Helpdesk Notification ไม่สร้าง `mail.mail`
- ตรวจว่า Incoming Email สำหรับสร้าง Ticket ยังทำงานได้โดยไม่เปิด Outbound Notification
- กำหนด Event, Recipient, Dedupe Key และ Notification Log ของ Helpdesk
- ตรวจสอบผลกระทบจาก User Notification Preference และ Followers
- จำกัดการ Reply และ Upload ตามสถานะ Ticket
- จำกัดชนิดและขนาดไฟล์แนบ
- ตรวจสอบ MIME Type, สิทธิ์ดาวน์โหลด, HTML Sanitization, CSRF และข้อมูลข้าม Company
- กำหนด Retention และการจัดการ Attachment ที่ไม่มี Record อ้างอิง

### เกณฑ์ผ่าน

- SLA ใช้เวลาทำงานตามปฏิทินบริษัท
- Pending User ไม่ทำให้ SLA เดินต่อ
- แจ้งเตือน Overdue ครั้งเดียวต่อเหตุการณ์
- ผู้เกี่ยวข้องได้รับ Activity ถูกต้อง
- ไม่มี Outbound Email เกิดจาก Helpdesk Activity/Chatter/Cron
- Incoming Email Intake ยังคงทำงานตาม Phase 1
- Portal ไม่สามารถดูหรือแก้ Ticket ของผู้อื่น
- Upload และข้อความจาก Portal ผ่าน Security Test

---

## ระยะที่ 5: พัฒนา IT Asset Registry สำหรับฝ่าย IT

### เป้าหมาย

พัฒนา IT Asset Registry ภายในสำหรับฝ่าย IT โดยเฉพาะ ไม่ใช่ Fixed Asset หรือสินทรัพย์ทางบัญชี

ข้อมูลในระบบนี้เป็นข้อมูลที่ฝ่าย IT บันทึกและดูแลเอง เพื่อใช้ติดตามอุปกรณ์และ Software License

ผู้ใช้งานทั่วไปจะไม่สามารถเปิดดูหรือค้นหา Asset เหล่านี้ได้

### ประเภท Asset ที่ต้องรองรับ

- Hardware: Computer, Laptop, Desktop, Printer, Monitor, Network Equipment และอุปกรณ์อื่น
- Software License: ชื่อผลิตภัณฑ์, Version, License Key, จำนวนสิทธิ์, วันเริ่มต้น และวันหมดอายุ

ควรออกแบบประเภทให้ขยายเพิ่มเติมได้ โดยไม่ต้องสร้างโมเดลใหม่ทุกครั้งที่มี Asset ประเภทใหม่

### ประเภทที่ยังไม่อยู่ในขอบเขต

- Google Email
- Microsoft Email
- User & Password หรือ System Account

ข้อมูลกลุ่มนี้ให้จัดการผ่าน Console ของแต่ละ Platform ไปก่อน และไม่พัฒนาฟังก์ชันเพิ่มในระยะนี้
หากมีข้อมูลเดิมอยู่ในฐานข้อมูล ห้ามลบทิ้งโดยอัตโนมัติ ให้สำรวจข้อมูลก่อนแล้วเลือกเก็บแบบอ่านอย่างเดียว,
Archive หรือซ่อนเมนูตามผลการตรวจสอบ

### แนวทางการออกแบบ Form และ Model ที่เลือกใช้

ให้ใช้ **Model เดียว** คือ `buz.it.asset` และใช้ `asset_type` เป็นตัวจำแนกประเภท Asset
จากนั้นแยกการใช้งานด้วย Form View, Action และ Menu ตามประเภท

โครงสร้างเมนูที่แนะนำ:

```text
IT Assets
├── Hardware
│   ├── Computers
│   └── Printers
└── Software Licenses
```

แต่ละเมนูควรมี `domain` จำกัดประเภท เช่น:

```xml
<field name="domain">[('asset_type', '=', 'software_license')]</field>
<field name="context">{'default_asset_type': 'software_license'}</field>
```

Form View ควรแสดงเฉพาะฟิลด์ที่เกี่ยวข้องกับประเภทนั้น โดยใช้ `invisible` ตาม `asset_type`
เช่น Serial Number และ Specification สำหรับ Hardware และ License Key, จำนวนสิทธิ์,
วันเริ่มต้น และวันหมดอายุสำหรับ Software License

เหตุผลที่เลือก Model เดียว:

- ใช้ประวัติ Asset ชุดเดียวกันได้
- ใช้ Security และ Audit Log รวมกันได้
- ทำรายงานและค้นหาข้อมูลรวมได้ง่าย
- เชื่อมโยงกับ Helpdesk Ticket ได้เหมือนกันทุกประเภท
- เพิ่ม Asset Type ใหม่ได้โดยไม่ต้องสร้าง Model ใหม่
- ลดความซ้ำซ้อนของโค้ดและการดูแลระบบ

ไม่แนะนำให้แยกเป็นหลาย Model ในระยะนี้ เว้นแต่ภายหลังมี Asset ประเภทใหม่ที่มีข้อกำหนด
ด้านข้อมูลและความปลอดภัยแตกต่างกันจนไม่สามารถใช้โครงสร้างร่วมกันได้

### ไฟล์หลัก

- `models/it_asset.py`
- `views/it_asset_views.xml`
- `security/it_asset_security.xml`
- `security/ir.model.access.csv`
- เพิ่มโมเดลประวัติ Asset และไฟล์ Test ที่เกี่ยวข้อง

### กติกาของระยะที่ 5

- ต้องทำตามลำดับ 5A → 5B → 5C → 5D
- เมื่อจบแต่ละระยะย่อย ให้หยุดและรอการตรวจรับ
- ห้ามเริ่ม Renewal/Notification ก่อน Asset Master, Security และ History ผ่าน
- Tests ของแต่ละระยะย่อยต้องรันและผ่านก่อนเริ่มระยะถัดไป

### ระยะที่ 5A: Architecture, Security และ Migration

#### งาน

- ยืนยันว่าใช้ Model เดียว `buz.it.asset` และเก็บใน Addon `buz_it_helpdesk` ในระยะนี้
- กำหนด Data Dictionary และ Required Field แยกตาม Hardware และ Software License
- กำหนด Role Matrix สำหรับ IT Asset User, IT Asset Manager และสิทธิ์ดู License Key
- จำกัด Menu, ACL, Record Rule, Export และ Download ตาม Role และ Company
- กำหนดผู้ใช้งาน Asset เป็น `hr.employee` และเก็บ `res.users` เป็นข้อมูลเชื่อมโยงเมื่อมี
- แยก End User, Department, Location และ IT Custodian
- ออกแบบ License Seat Allocation พร้อมจำนวนทั้งหมด, ใช้งานแล้ว และคงเหลือ
- ออกแบบ Archive/Retention โดยห้ามลบ Asset, History และ Renewal ที่ใช้งานจริง
- สำรวจข้อมูล `email` และ `system_account` เดิม
- จัดทำ Migration Mapping เพื่อ Archive, ซ่อนเมนู หรือเก็บแบบอ่านอย่างเดียว โดยไม่ลบข้อมูล
- จัดทำ Import Template, Duplicate Detection, Dry Run และ Rollback Plan

#### เกณฑ์ผ่าน

- Data Model และ Role Matrix ได้รับการยืนยัน
- Requester และ Portal User ไม่สามารถค้นหา อ่าน Export หรือดาวน์โหลดข้อมูล IT Asset
- Agent ต่าง Company ไม่สามารถเข้าถึง Asset ผ่าน UI หรือ RPC/API
- Migration Dry Run ไม่ทำข้อมูลเดิมสูญหาย
- มีรายงานข้อมูลเดิมและ Rollback Plan

### ระยะที่ 5B: Asset Master และ Form แยกประเภท

#### งาน

- ปรับ Asset Master ให้รองรับ Hardware และ Software License
- สร้าง Form View, List, Search, Action และ Menu แยกตามประเภท โดยไม่สร้าง Model ซ้ำ
- เพิ่มข้อมูล Hardware: Serial, Brand, Model, Specification, Purchase, Warranty, Vendor และ Location
- เพิ่มข้อมูล Software License: Product, Version, License Key, จำนวน Seat, วันเริ่มต้น และวันหมดอายุ
- เพิ่ม Constraint ตามประเภทและ Company
- ป้องกัน Duplicate Serial และ Duplicate License Record ตามกติกาที่กำหนด
- ซ่อน Google/Microsoft Email และ System Account จากเมนูใหม่
- จำกัด License Key ไม่ให้ปรากฏใน List, Kanban, Search, Report, Chatter และ Notification

#### เกณฑ์ผ่าน

- สร้างและแก้ไข Hardware/Software License ผ่าน Form แยกประเภทได้
- Required Field และ Constraint ทำงานเหมือนกันทั้ง UI และ API
- เมนูประเภทนอกขอบเขตไม่ปรากฏ แต่ข้อมูลเดิมไม่ถูกลบ
- License Key เข้าถึงได้เฉพาะกลุ่มที่กำหนด
- Install, Upgrade และ Tests ของ 5B ผ่าน

### ระยะที่ 5C: Assignment, Repair และ History

#### งาน

- เพิ่มโมเดล `buz.it.asset.log` สำหรับประวัติแบบแก้ไขย้อนหลังไม่ได้
- เพิ่ม Assignment/Return สำหรับ Employee และ IT Custodian
- เพิ่ม License Seat Allocation และป้องกันจัดสรรเกินจำนวน
- บันทึกการเปลี่ยน User, Department, Location, Status และ Custodian
- เพิ่ม `Send to Repair`, `Repair Done`, `Mark Lost`, `Recover` และ `Retire`
- บันทึก Vendor ซ่อม, วันที่ส่ง, วันที่รับคืน, ค่าใช้จ่าย, อาการ, ผลการซ่อม และไฟล์หลักฐาน
- เชื่อม Asset และประวัติการซ่อมกับ Helpdesk Ticket
- ห้าม Assign Asset ที่ Repair, Lost, Retired หรือ Expired
- ใช้ Archive แทน Delete และป้องกันการลบ History

#### เกณฑ์ผ่าน

- ทุก Action สร้าง History พร้อมผู้ดำเนินการและเวลา
- License Allocation ไม่เกินจำนวน Seat
- Asset ที่มีสถานะต้องห้ามไม่สามารถ Assign ผ่าน UI หรือ API
- Repair และ Helpdesk Ticket ตรวจสอบย้อนหลังได้
- Agent ไม่มีสิทธิ์แก้หรือลบ History
- Tests ของทุก Action และ Forbidden Transition ผ่าน

### ระยะที่ 5D: Renewal และ Notification

#### งาน

- เพิ่มโมเดล `buz.it.asset.renewal`
- รองรับ `Pending Review`, `Renewal In Progress`, `Renewed`, `Expired` และ `Cancelled`
- บันทึก Owner, Vendor, ค่าใช้จ่าย, Currency, วันที่เริ่ม, วันที่สำเร็จ และเลขที่เอกสาร
- แนบใบเสนอราคา, Purchase Order, Invoice, ใบเสร็จ, License Certificate และ Email ยืนยัน
- บังคับวันหมดอายุใหม่และหลักฐานก่อนเปลี่ยนเป็น `Renewed`
- อัปเดต Asset และปิดรอบ Notification เดิมใน Transaction เดียว
- สร้างรอบแจ้งเตือน 90/60/30 วันและ Expired
- ใช้ Email เป็น External Channel ของ IT Asset และสร้าง Activity/Chatter ควบคู่
- เพิ่ม Notification Log, Dedupe Key, Retry และ Error Detail
- รองรับ Catch-up หาก Cron ไม่ได้ทำงานตรงวันครบกำหนด
- ใช้ Timezone และ Recipient Configuration แยกตาม Company
- ตรวจ Mail Queue และสร้าง Activity ให้ IT Manager เมื่อส่ง Email ล้มเหลว
- ห้ามส่ง License Key หรือข้อมูลลับใน Subject/Body/Attachment ของ Notification

#### เกณฑ์ผ่าน

- 90/60/30/Expired ส่งครั้งเดียวต่อรอบและไม่พลาดเมื่อ Cron หยุดชั่วคราว
- ส่ง Email สำเร็จพร้อม Activity/Chatter และมี Notification Log
- การส่งล้มเหลวถูก Retry และตรวจสอบย้อนหลังได้
- `Renewed` ปิดรอบเดิมและเริ่มรอบใหม่อย่างถูกต้อง
- Multi-company, Timezone และ Recipient Tests ผ่าน
- ไม่มี License Key ปรากฏใน Mail Queue หรือ Notification Log

### หลักการจัดเก็บข้อมูลลับ

- ห้ามแสดง License Key ใน List, Kanban, Search หรือ Report
- ใช้ field access group แยกข้อมูลลับจากข้อมูลทั่วไป
- ไม่บันทึก License Key เดิมลงในประวัติหรือ Chatter
- พิจารณาใช้การเข้ารหัสหรือ Vault Reference หาก License Key มีความสำคัญสูง
- การเปิดดูหรือแก้ไขข้อมูลลับควรอยู่ในสิทธิ์ Manager และต้องตรวจสอบ Audit Log

### ประวัติ Asset ที่ต้องบันทึก

ทุกเหตุการณ์ควรบันทึกข้อมูลต่อไปนี้:

- Asset ที่เกี่ยวข้อง
- ประเภทเหตุการณ์
- วันที่และเวลาที่เกิดเหตุการณ์
- ผู้ดำเนินการ
- ผู้รับผิดชอบเดิมและใหม่
- Department เดิมและใหม่
- Location เดิมและใหม่
- สถานะเดิมและใหม่
- Helpdesk Ticket ที่เกี่ยวข้อง
- หมายเหตุและไฟล์แนบ

### ระบบต่ออายุและหลักฐาน

Asset ประเภท Software License สามารถมีประวัติการต่ออายุได้หลายรอบ
จึงควรเก็บข้อมูลการต่ออายุเป็นรายการแยกจาก Asset หลัก เช่น:

```text
Adobe Creative Cloud
├── Renewal 2024 — Renewed
├── Renewal 2025 — Renewed
└── Renewal 2026 — Renewal In Progress
```

สถานะการต่ออายุที่ต้องรองรับ:

```text
Not Required
Pending Review
Renewal In Progress
Renewed
Expired
Cancelled
```

ไฟล์หลักฐานที่สามารถแนบได้:

- ใบเสนอราคา
- Purchase Order
- Invoice และใบเสร็จ
- License Certificate
- Email ยืนยันการต่ออายุ
- เอกสารจาก Vendor
- Screenshot หลักฐานการต่ออายุ

เมื่อรายการต่ออายุเปลี่ยนเป็น `Renewed` ระบบต้องตรวจสอบวันหมดอายุใหม่,
อัปเดต Asset หลัก, บันทึกผู้ดำเนินการและวันที่, เก็บไฟล์หลักฐาน,
ปิดการแจ้งเตือนของรอบเดิม และเริ่มรอบแจ้งเตือนใหม่ที่ 90/60/30 วัน
ก่อนวันหมดอายุใหม่

### เกณฑ์ผ่าน

- ทุกการเปลี่ยนสถานะสร้างประวัติ
- ทุกการเปลี่ยนผู้รับผิดชอบ, Department และ Location สร้างประวัติ
- ประวัติระบุผู้ดำเนินการและวันที่ได้
- IT Asset User และ IT Asset Manager เห็นข้อมูล Asset ตาม Company ที่ได้รับอนุญาต
- Requester และ Portal User ไม่สามารถเปิดดูหรือค้นหา IT Asset ได้
- License Key ไม่ปรากฏใน List, Search, Kanban หรือ Report
- Asset ที่หมดอายุ, Retired หรืออยู่ระหว่างซ่อมไม่สามารถ Assign ซ้ำได้โดยอัตโนมัติ
- รายการต่ออายุที่ `Renewed` ต้องมีวันหมดอายุใหม่และหลักฐานอย่างน้อยหนึ่งรายการ
- การต่ออายุแต่ละรอบต้องตรวจสอบย้อนหลังได้โดยไม่ทับประวัติรอบก่อนหน้า
- การต่ออายุสำเร็จต้องเริ่มรอบแจ้งเตือน 90/60/30 วันใหม่อย่างถูกต้อง
- Asset ที่อยู่ระหว่างซ่อมไม่สามารถ Assign ซ้ำได้
- Asset ที่ Retired ไม่สามารถกลับมาใช้งานโดยไม่ผ่านสิทธิ์ Manager
- มี Test สำหรับทุก Action

---

## ระยะที่ 6: IT Management Unified Dashboard

### เป้าหมาย

สร้าง Dashboard หลักหนึ่งหน้า มี Sidebar สำหรับ Overview, Helpdesk และ IT Asset
โดยโหลดข้อมูลตามสิทธิ์และเฉพาะหน้าที่ผู้ใช้เลือก

### โครงสร้าง

```text
IT Management Dashboard
├── Overview
├── Helpdesk
└── IT Asset
```

### งาน

- สร้าง OWL Client Action หลักและ Sidebar
- ใช้ Helpdesk Dashboard ปัจจุบันเป็นส่วนย่อยโดยไม่ทำลาย Drill-down เดิม
- เพิ่ม Overview: Open Ticket, SLA Overdue, Asset In Use, Under Repair และ License Expiring
- เพิ่ม Helpdesk: Created vs Resolved, Backlog, SLA Compliance, First Response และ Resolution Time
- เพิ่ม IT Asset: สถานะ, ประเภท, Department, Repair และ License Expiring
- กำหนด Filter กลางสำหรับ Company และช่วงเวลา
- โหลดข้อมูลแบบ Lazy Loading เฉพาะหน้าที่เลือก
- ทุก KPI ต้องกดเปิดรายการต้นทางด้วย Domain ที่ถูกต้อง
- ตรวจสิทธิ์ Server-side ทุก Method ห้ามพึ่งการซ่อนเมนูเพียงอย่างเดียว
- ป้องกัน Dashboard แสดง License Key หรือข้อมูลลับ
- เพิ่ม Index/ปรับ Query และทดสอบ Performance กับข้อมูลจำลองตามปริมาณคาดการณ์
- รองรับหน้าจอขนาดเล็กและ Error/Empty/Loading State

### เกณฑ์ผ่าน

- Agent และ Manager เห็นเฉพาะ Dashboard ที่ได้รับอนุญาต
- Requester ไม่เห็น IT Asset Dashboard
- KPI ตรงกับข้อมูลใน List/Pivot ที่เป็นแหล่งอ้างอิง
- Drill-down และ Filter ไม่ข้าม Company
- การสลับหน้าไม่โหลดข้อมูลส่วนที่ยังไม่ได้เลือก
- Dashboard ไม่มีข้อมูลลับและผ่าน Performance Baseline

---

## ระยะที่ 7: เพิ่ม Test, Security Review และ UAT

### เป้าหมาย

ยืนยันว่าการแก้ไขไม่ทำให้ฟังก์ชันเดิมเสียหาย

### งาน

- เพิ่ม Test สำหรับทุก Bug ที่พบ
- เพิ่ม Test สำหรับ Multi-company
- เพิ่ม Test สำหรับ Email Intake
- เพิ่ม Test สำหรับ Portal และ Attachment
- เพิ่ม Test สำหรับ Ticket Workflow
- เพิ่ม Test สำหรับ SLA และ Cron
- เพิ่ม Test สำหรับ IT Asset History
- เพิ่ม Test สำหรับ Renewal, Notification Retry, Catch-up และ Dedupe
- เพิ่ม Test สำหรับ License Seat Allocation
- เพิ่ม Test สำหรับ Role Matrix และผู้ใช้ที่มีเฉพาะ Manager
- เพิ่ม Test ว่า Helpdesk ไม่สร้าง Outbound Email
- เพิ่ม Test สำหรับ Archive/Delete Protection
- เพิ่ม Test สำหรับ Migration และข้อมูล Asset ประเภทเดิม
- เพิ่ม Test สำหรับ Dashboard KPI, Drill-down และ Multi-company
- ตรวจ XSS, CSRF, Attachment Access, MIME Type และ File Size
- ตรวจว่าข้อมูลลับไม่ปรากฏใน Export, Log, Chatter, Report หรือ Mail Queue
- รัน Test บนฐานข้อมูลทดสอบแยก
- ตรวจสอบ XML View และ Access Rights
- รัน Lint และแก้ Error ระดับ Critical/High
- ทดสอบ Install ใหม่, Upgrade จาก Snapshot และ Uninstall เฉพาะบนฐานทดสอบ
- จัดทำ UAT Scenario แยกตาม Requester, Agent, Manager และ IT Asset Manager
- ให้ผู้ใช้ธุรกิจลงนามผล UAT และ Known Issues

### เกณฑ์ผ่าน

- Tests ผ่านทั้งหมด
- ไม่มี Required Field Error
- ไม่มี AccessError ที่ไม่คาดหมาย
- ไม่มี XML Parse Error
- ไม่มี Python Traceback
- ไม่มี Regression จากฟังก์ชันเดิม
- Security Matrix, Migration และ Notification Tests ผ่าน
- Dashboard KPI ตรงกับ Source Records
- UAT ผ่านและมีหลักฐานการอนุมัติ
- Known Issues ที่เหลือไม่มีระดับ Critical หรือ High

---

## ระยะที่ 8: ออกแบบขั้นตอน UAT ทั้งฝั่ง User และ IT

### เป้าหมาย

ออกแบบกระบวนการ UAT ให้ครอบคลุมการใช้งานจริงของ User และการปฏิบัติงานของ IT
โดยกำหนดบทบาท ขั้นตอนทดสอบ หลักฐาน และเกณฑ์การอนุมัติให้ตรวจสอบย้อนกลับได้

### งาน

#### 8.1 ขั้นตอนร่วมก่อนเริ่ม UAT

- ระบุ Scope, Objective, Environment, Version และวันที่ทดสอบให้ชัดเจน
- จัดเตรียม UAT Scenario, Test Data, User Account และ Role ที่ใช้ทดสอบ
- กำหนดผู้รับผิดชอบ ผู้อนุมัติ ช่องทางแจ้งปัญหา และรอบเวลาการทดสอบ
- กำหนดรูปแบบหลักฐาน เช่น Screenshot, Ticket Number, Activity, Chatter, Email และผลจาก Dashboard
- กำหนดระดับ Severity, วิธีบันทึก Defect, ผู้รับผิดชอบแก้ไข และเกณฑ์ Retest

#### 8.2 ขั้นตอน UAT ฝั่ง User

1. User ตรวจสอบการเข้าสู่ระบบและการมองเห็นเมนูตามสิทธิ์ของตนเอง
2. User สร้าง Ticket พร้อมข้อมูลที่จำเป็น Attachment และรายละเอียดปัญหา
3. User ตรวจสอบการส่ง Ticket การได้รับเลขที่ Ticket และการแสดงสถานะ
4. User ติดตามการมอบหมายงาน การตอบกลับ การขอข้อมูลเพิ่ม และการเปลี่ยนสถานะ
5. User ตรวจสอบ SLA, กำหนดเวลา, Notification และประวัติการสื่อสารใน Chatter
6. User ทดสอบการปิดงาน การเปิด Ticket เดิมกลับมาติดตาม และการค้นหาข้อมูล
7. User ทดสอบกรณีที่เกี่ยวข้องกับ IT Asset เช่น การแจ้งซ่อม การยืมคืน และข้อมูลอุปกรณ์
8. User บันทึกผล Actual Result, Expected Result, หลักฐาน และข้อเสนอแนะใน UAT Sheet

#### 8.3 ขั้นตอน UAT ฝั่ง IT

1. IT ตรวจสอบการรับ Ticket การจัดลำดับความสำคัญ และการมอบหมายผู้รับผิดชอบ
2. IT ตรวจสอบ Workflow ตั้งแต่ New, In Progress, Pending User จนถึง Resolved/Closed
3. IT ทดสอบ SLA, Activity, Notification, Cron, Retry, Catch-up และการป้องกันการแจ้งเตือนซ้ำ
4. IT ตรวจสอบสิทธิ์ของ Agent, Manager และ IT Asset Manager รวมถึง Multi-company
5. IT ทดสอบการจัดการ Attachment, Asset History, Repair, Renewal และ License Seat Allocation
6. IT ตรวจสอบ Dashboard KPI, Drill-down, Filter และความถูกต้องเมื่อเปรียบเทียบกับ Source Records
7. IT ตรวจสอบ Log, Mail Queue, Failure Activity และข้อมูลลับที่ไม่ควรแสดง
8. IT ตรวจสอบการแก้ไข Defect, Retest, Regression และบันทึกผลการทดสอบแต่ละ Scenario

#### 8.4 ขั้นตอนสรุปผลและอนุมัติ

- IT รวบรวมผล UAT ของ User และ IT แยกตาม Scenario และ Severity
- Defect ที่ไม่ผ่านต้องมีผู้รับผิดชอบ กำหนดวันแก้ไข และผล Retest
- User ยืนยันผลด้านกระบวนการใช้งาน ส่วน IT ยืนยันผลด้าน Workflow, Security และ Technical Operation
- จัดทำ UAT Summary พร้อมรายการ Passed, Failed, Deferred และ Known Issues
- ขออนุมัติ UAT จากตัวแทน User และผู้รับผิดชอบ IT ก่อนส่งต่อไปยังระยะถัดไป

### เกณฑ์ผ่าน

- มี UAT Scenario และ Test Data ครบทั้งฝั่ง User และ IT
- User และ IT ดำเนินการตามขั้นตอนและบันทึกหลักฐานครบทุก Scenario
- ไม่มี Critical หรือ High Severity Defect ที่ยังไม่มีแผนแก้ไขและกำหนด Retest
- ผล Workflow, Security, Notification, Asset และ Dashboard ผ่านตาม Acceptance Criteria
- ผล UAT ถูกสรุปแยกเป็น Passed, Failed, Deferred และ Known Issues
- มีการอนุมัติผล UAT จากตัวแทน User และผู้รับผิดชอบ IT
- เอกสาร UAT สามารถตรวจสอบย้อนกลับจาก Scenario ไปยังหลักฐานและ Defect ได้
---

## วิธีสั่งให้ Codex ทำงานทีละระยะ

ตัวอย่างคำสั่ง:

```text
อ่านไฟล์ IT_HELPDESK_IMPROVEMENT_PLAN.md และทำเฉพาะระยะที่ 1 เท่านั้น
ห้ามทำงานข้ามระยะ แก้ไขโค้ดและเพิ่ม Test ตามเกณฑ์ผ่านของระยะนี้
รันการตรวจสอบที่ทำได้ แล้วหยุดรอคำสั่งถัดไป
```

ตัวอย่างสำหรับระยะย่อย IT Asset:

```text
อ่านไฟล์ IT_HELPDESK_IMPROVEMENT_PLAN.md และทำเฉพาะระยะที่ 5A เท่านั้น
ห้ามเริ่ม 5B, 5C หรือ 5D จนกว่าฉันจะตรวจรับ
แก้ไขและทดสอบตาม Acceptance Criteria ของ 5A แล้วสรุปผลตามรูปแบบรายงานในเอกสาร
```

เมื่อระยะหนึ่งเสร็จ ให้ตรวจสอบผลก่อนจึงสั่งระยะถัดไป
