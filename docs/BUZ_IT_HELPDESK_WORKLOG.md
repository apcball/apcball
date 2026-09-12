# BUZ IT Helpdesk Worklog

เอกสารติดตามสถานะงานของโมดูล `buz_it_helpdesk`

วันที่อัปเดตล่าสุด: 2026-09-12  
สถานะโมดูลปัจจุบัน: `17.0.1.3.5`  
ขอบเขต: บันทึกสิ่งที่มีอยู่แล้ว สิ่งที่ตรวจสอบแล้ว และงานที่ต้องดำเนินการต่อ

## สรุปปัจจุบัน

- โมดูลมีโครงสร้างหลักครบสำหรับ Helpdesk, workflow, security, LINE integration และ frontend assets
- Ticket workflow ปัจจุบันมี 6 สถานะ:
  `Draft → New → In Progress → Pending User → Resolved → Closed`
- Requester ยังคงเห็น Ticket ทั้งหมดภายในบริษัทตามพฤติกรรมปัจจุบัน
- Working tree ของ `buz_it_helpdesk` สะอาด ณ วันที่ตรวจสอบ
- งานล่าสุดที่ต้องทำ: ซ่อนคอลัมน์ `Draft` จากหน้า Ticket Kanban เป็นค่าเริ่มต้น แต่ยังเปิดกลับได้จากการตั้งค่า Stage

## สิ่งที่ทำเสร็จแล้ว

### โครงสร้างโมดูล

- มี `models/` สำหรับ Ticket, Stage, Team, Category และ LINE composer
- มี `services/line_service.py` สำหรับ logic การเชื่อมต่อ LINE
- มี `controllers/line_webhook.py` สำหรับรับ LINE webhook
- มี `views/`, `security/`, `data/`, `migrations/`, `static/` และ `tests/`
- Manifest ระบุ dependencies หลักเป็น `base`, `hr` และ `mail`
- `buz_it_asset` เชื่อมต่อกับ Helpdesk ผ่าน model inheritance ของ `buz.helpdesk.ticket`

### Helpdesk workflow

- มีการควบคุมการเปลี่ยนสถานะตามลำดับ workflow
- รองรับการรับ Ticket, มอบหมายผู้รับผิดชอบ, รอผู้ใช้, กลับมาทำงานต่อ, Mark Resolved และ Close Ticket
- ใช้ Chatter และ Activities สำหรับการติดตาม Ticket
- มีการป้องกันการแก้ไข field ระบบ เช่น เลข Ticket, Company, Requester และวันที่ระบบ
- มีการตรวจสอบว่า Assigned User ต้องอยู่ใน Team ที่เลือก

### LINE integration

- รองรับ LINE Bot configuration ระดับบริษัท
- รองรับการเชื่อม LINE account ของ Requester ด้วย one-time connection code
- มีการตรวจสอบ webhook signature
- มีการส่ง notification เมื่อสร้าง Ticket และเมื่อ Ticket เข้าสู่ขั้นตอนที่เกี่ยวข้อง
- LINE failure ไม่ทำให้การสร้างหรือเปลี่ยน workflow ของ Ticket rollback
- มีการป้องกันไม่ให้ token ถูกส่งกลับไปยัง Browser

### Kanban visibility

- มี field `show_in_kanban` ใน model `buz.helpdesk.stage`
- มี checkbox `แสดงใน Kanban / Show in Kanban` ในหน้า Stage configuration
- Backend group expansion และ frontend Kanban visibility ใช้ field นี้ในการกรองคอลัมน์
- มี test รองรับกรณี stage ถูกซ่อนจาก Kanban

### การตรวจสอบล่าสุด

- ตรวจสอบโครงสร้างไฟล์ของโมดูลแล้ว
- ตรวจสอบ manifest และลำดับการโหลด data, security และ views แล้ว
- XML ของโมดูล parse ผ่าน
- พบ automated test ทั้งหมด 46 test methods ใน `tests/`
- ยังไม่ได้รัน Odoo isolated test หรือ Browser/PDF UAT ในรอบการตรวจโครงสร้างล่าสุด

## งานที่ต้องทำ

### ลำดับที่ 1: ซ่อน Draft จาก Ticket Kanban เป็นค่าเริ่มต้น

สถานะ: `เสร็จแล้ว`

รายละเอียดที่ต้องทำ:

- ตั้งค่า `show_in_kanban` ของ XML ID `buz_it_helpdesk.stage_draft` เป็น `False`
- คง checkbox `Show in Kanban` ไว้ เพื่อให้ Helpdesk Manager เปิดคอลัมน์ Draft กลับมาได้เอง
- เพิ่มหรือปรับ test ให้ยืนยันว่า Draft มีค่าเริ่มต้นเป็นซ่อน
- ตรวจว่า Ticket ที่อยู่ใน Draft ไม่ถูกลบและยังเปิดจาก list/form ได้
- ตรวจว่า workflow และปุ่ม `Create Ticket` ยังทำงานเหมือนเดิม

ผลที่คาดหวัง:

- หน้า Kanban ไม่แสดงคอลัมน์ `Draft` โดยค่าเริ่มต้น
- Ticket Draft ยังอยู่ในระบบตามเดิม
- หากต้องการดู Draft ให้เปิด `Show in Kanban` จาก Stage configuration
- Stage อื่นไม่เปลี่ยนแปลง

ขอบเขตที่ไม่รวมในงานนี้:

- ไม่เปลี่ยน workflow
- ไม่ลบหรือ archive Stage Draft
- ไม่เปลี่ยนสิทธิ์การมองเห็น Ticket
- ไม่เปลี่ยนการทำงานของ LINE

### ลำดับที่ 2: ตรวจสอบการแจ้งเตือนข้ามบริษัท

สถานะ: `ควรตรวจสอบก่อนงาน security รอบถัดไป`

จุดที่พบจาก source ปัจจุบัน:

- `action_create_ticket()` ค้นหา active Support Agent โดยยังไม่มีเงื่อนไขจำกัดบริษัท
- อาจทำให้ Activity หรือการแจ้งเตือนถูกส่งไปยัง Support Agent ของบริษัทอื่น

สิ่งที่ต้องตัดสินใจและทดสอบ:

- จำกัด Support Agent ตาม `company_id` ของ Ticket หรือ
- อนุญาต shared support อย่างชัดเจนและกำหนดขอบเขตผู้รับ
- เพิ่ม test สำหรับหลายบริษัท

### ลำดับที่ 3: เพิ่มการทดสอบสิทธิ์และข้อมูลแนบ

สถานะ: `ยังไม่ตรวจครบ`

- ทดสอบสิทธิ์ Requester ผ่าน backend/RPC ไม่ใช่เฉพาะปุ่มบนหน้าเว็บ
- ยืนยันว่า Requester แก้ไขได้เฉพาะ field ที่อนุญาต
- ตรวจการเข้าถึง Attachment และ Chatter ของ Ticket ผ่าน URL หรือ request โดยตรง
- ยืนยันพฤติกรรมการเห็น Ticket ทั้งบริษัทตาม requirement ปัจจุบัน

### ลำดับที่ 4: ปรับปรุงการดูแลรักษาโค้ด

สถานะ: `ยังไม่เร่งด่วน`

- `models/helpdesk_ticket.py` มี logic หลายด้านรวมกัน ได้แก่ field, workflow, permission, activity และ LINE
- หากมีการเพิ่มฟีเจอร์ต่อเนื่อง ควรพิจารณาแยก logic เป็นส่วนย่อยเพื่อลดความเสี่ยงในการแก้ไข
- ยังไม่ควร refactor เพียงเพื่อความสวยงามก่อนงาน functional และ security ที่สำคัญกว่า

## ขอบเขตการส่งมอบ

- การแก้ source และการตรวจ local เป็นคนละขั้นตอนกับการ deploy DEV
- การทำงานในเอกสารนี้ยังไม่ได้อนุมัติการ deploy, upgrade, restart หรือ Production change
- หากมีการ deploy ต้องระบุ module, database, server และขั้นตอน upgrade/restart แยกต่างหาก
- Static check, registry check และ automated test ไม่ถือเป็นหลักฐานของ Browser/PDF/accounting UAT

## ประวัติการอัปเดต

| วันที่ | รายการ | สถานะ |
|---|---|---|
| 2026-09-12 | ตรวจสอบโครงสร้าง `buz_it_helpdesk` และความสัมพันธ์ของ models, views, security, services และ tests | เสร็จแล้ว |
| 2026-09-12 | ยืนยันให้ Requester เห็น Ticket ทั้งบริษัทตามพฤติกรรมเดิม | ยืนยันแล้ว |
| 2026-09-12 | ซ่อน `Draft` จาก Kanban โดยค่าเริ่มต้น พร้อมยืนยันการเปิดกลับผ่าน Stage configuration และการคงอยู่ของ Ticket Draft | เสร็จแล้ว |

## Approval Sub-workflow (2026-09-12)

- เพิ่ม Approval Manager, Approval Status, request note และ audit timestamps สำหรับทีม IT
- เพิ่ม Send to Approve, Approve และ Reject wizard ที่บังคับเหตุผล พร้อม Activity และ Chatter audit
- ตรวจสิทธิ์ซ้ำใน backend/RPC, จำกัด Manager ตามกลุ่มและบริษัท และล็อกฟิลด์ระหว่างคำขอ pending
- Targeted `TestTicketApproval` ผ่าน; full module suite ยังมี failure/error เดิมใน LINE และ Kanban tests ที่ไม่เกี่ยวกับ Approval
