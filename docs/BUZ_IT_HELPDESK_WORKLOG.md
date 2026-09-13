# BUZ IT Helpdesk Worklog

## การแก้ไขล่าสุด: Resolution Confirmation ไม่ขึ้นกับภาษา

- เพิ่ม Activity Type เฉพาะชื่อ `Resolution Confirmation`
- การสร้างและค้นหา Activity ใหม่อ้างอิง Activity Type แทนข้อความสรุปที่อาจถูกแปล
- Activity เดิมที่ใช้ประเภท To Do ยังรองรับด้วย fallback
- ไม่กระทบ Approval Activity, workflow, สิทธิ์, LINE หรือ SLA
- แก้ไขและตรวจสอบเฉพาะใน local repository
- ห้าม deploy, upload, upgrade module, restart service, migration หรือแก้ฐานข้อมูลจริง

## ข้อกำหนดที่ยืนยันแล้ว

### Helpdesk Team และการดูแลหลายบริษัท

- มีทีม IT กลางเพียงทีมเดียว
- ทีม IT กลางสามารถรับผิดชอบ Ticket จากหลายบริษัทได้
- ไม่ต้องเพิ่ม `company_id` ให้กับ Helpdesk Team
- ไม่ต้องจำกัดการแจ้งเตือนหรือการรับงานเฉพาะบริษัทของ Ticket
- การตรวจสอบสิทธิ์ควรยืนยันว่าเจ้าหน้าที่เป็นสมาชิกของทีม IT กลาง และมีสิทธิ์เข้าถึงบริษัทที่เกี่ยวข้อง

เอกสารติดตามสถานะงานของโมดูล `buz_it_helpdesk`

วันที่อัปเดตล่าสุด: 2026-09-12  
สถานะโมดูลปัจจุบัน: `17.0.1.3.6`
ขอบเขต: บันทึกสิ่งที่มีอยู่แล้ว สิ่งที่ตรวจสอบแล้ว และงานที่ต้องดำเนินการต่อ

## สรุปปัจจุบัน

- โมดูลมีโครงสร้างหลักครบสำหรับ Helpdesk, workflow, security, LINE integration และ frontend assets
- Ticket workflow ปัจจุบันมี 6 สถานะ:
  `Draft → New → In Progress → Pending User → Resolved → Closed`
- Requester ยังคงเห็น Ticket ทั้งหมดภายในบริษัทตามพฤติกรรมปัจจุบัน
- มีการ commit งาน Helpdesk ของวันที่ 2026-09-12 ต่อเนื่องถึง `db1e1765`
- DEV `MOG_DEV` อัปเกรดโมดูลเป็น `17.0.1.3.6` และ restart container `odoo` แล้ว; HTTP health check ได้ `200`

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
| 2026-09-12 | รองรับ Legacy Ticket ที่ไม่มี Category/Priority และปรับเงื่อนไข View/Backend ให้สอดคล้องกัน | เสร็จแล้ว |

## Approval Sub-workflow (2026-09-12)

- Commits: `f4bc3317`, `1493d48e`
- เพิ่ม Approval Manager, Approval Status, request note และ audit timestamps สำหรับทีม IT
- เพิ่ม Send to Approve, Approve และ Reject wizard ที่บังคับเหตุผล พร้อม Activity และ Chatter audit
- ตรวจสิทธิ์ซ้ำใน backend/RPC, จำกัด Manager ตามกลุ่มและบริษัท และล็อกฟิลด์ระหว่างคำขอ pending
- Targeted `TestTicketApproval` ผ่าน; full module suite ยังมี failure/error เดิมใน LINE และ Kanban tests ที่ไม่เกี่ยวกับ Approval

## SLA and Attachments Layout (2026-09-12)

- ย้ายส่วน SLA ไปอยู่คอลัมน์ที่ 2 ของ Attachments ในฟอร์ม Ticket โดยคง `attachment_ids`, Attachment Composer และฟิลด์ SLA เดิม
- เพิ่ม Responsive Layout: หน้าจอกว้างแสดง Attachments ทางซ้ายและ SLA ทางขวา; หน้าจอแคบให้ SLA อยู่ใต้ Attachments
- คงสิทธิ์การมองเห็น SLA เฉพาะ IT Support Agent และ Helpdesk Manager และคง Approval group ในตำแหน่งเดิม
- ไม่เปลี่ยน SLA calculation, Attachment, Workflow, Approval sub-workflow หรือสิทธิ์อื่น
- ตรวจ XML parse, XML structure/XPath, manifest asset load, SLA fields แบบอ่านอย่างเดียว และ `git diff --check` ผ่าน
- ยังไม่ได้ทำ Browser UAT ในรอบนี้ จึงยังไม่ยืนยันผลการจัดวางบน Desktop/หน้าจอแคบหรือการใช้งาน Upload, Paste Screenshot, Preview, Download และ Remove จาก Browser
- Commit: `db1e1765` (`feat: enhance SLA and attachments layout in ticket form with responsive design`)
- DEV deployment: upload, upgrade และ restart สำเร็จ; module state เป็น `installed`, version `17.0.1.3.6`, container เป็น `Up`

## SLA Management (2026-09-12)

- Commit: `9ed41bff` (`feat: implement SLA management with configuration, rules, and holiday handling`)
- เพิ่ม SLA Settings ต่อบริษัท, working hours, lunch hours, timezone และ company holidays
- เพิ่ม SLA Rules ที่เลือกตาม Category/Priority และคำนวณ response/resolution deadline ตามเวลาทำงาน
- Ticket บันทึก SLA start, response และ resolution timestamps ตาม workflow พร้อมสถานะ On Track, Paused, Overdue, Resolved และ No SLA
- เพิ่ม access control และ automated tests สำหรับ rule specificity, business time และการจำกัดสิทธิ์ SLA Settings

## Attachment Composer (2026-09-12)

- Commits: `3cbcd251`, `8d4c5a58`
- เพิ่ม Attachment Composer สำหรับ `attachment_ids` รองรับ Upload และ Paste Screenshot ผ่าน Clipboard
- คง Preview, Download และ Remove ของ Attachment เดิม และเพิ่มการแสดงชนิดไฟล์/จำนวนไฟล์
- ยังไม่มี Browser UAT ในรอบนี้ จึงยังไม่ยืนยันพฤติกรรมการใช้งานจริงจาก Browser

## Legacy Ticket SLA Setup (2026-09-12)

- เปิดให้ Helpdesk Manager เติม Category ของ Ticket เดิมที่ข้อมูล SLA ยังไม่ครบได้เท่านั้น
- หาก Priority ของ Ticket เดิมไม่มีค่า ระบบใช้ `Normal` (`1`) เป็นค่าเริ่มต้น
- เมื่อ Category/Priority ครบจากการแก้ไขครั้งแรก ระบบเริ่ม `sla_start_at` จากเวลาบันทึกจริง ไม่คำนวณย้อนหลังจาก `create_date`
- Ticket ที่ Receive แล้วบันทึก `sla_response_at` เท่ากับเวลาเริ่ม SLA เพื่อไม่คิด Response SLA ย้อนหลัง
- Ticket ที่ Resolved/Closed แล้ว และ Ticket ที่ข้อมูลครบแต่ไม่เคยเริ่ม SLA จะยังคง `No SLA`
- ปรับ View flag `can_edit_category_priority` และ Backend guard ให้เปิดแก้เฉพาะกรณี Legacy ที่จำเป็น; Ticket ใหม่ยังบังคับ Category และ Priority เริ่มต้นเป็น Normal
- เพิ่ม targeted tests สำหรับ Legacy category/priority, auto-start, no-retroactive response, terminal ticket และสิทธิ์ Agent
- Python AST, XML parse, `git diff --check` ผ่าน; isolated Odoo `TestHelpdeskSla` ผ่าน `0 failed, 0 error(s) of 9 tests`
- ยังไม่ได้ทำ Browser UAT และงานรอบนี้ยังไม่ได้ deploy, upgrade หรือ restart DEV/Production

## DEV Delivery (2026-09-12)

## SLA Stability Hardening (2026-09-13)

## Requester Draft Ownership (2026-09-13)

- จำกัด Requester ให้แก้ไขได้เฉพาะ Ticket สถานะ Draft ที่มีตนเองเป็น Requester
- ป้องกันการแก้ไข Draft ของผู้อื่นที่ Backend/API/RPC ด้วย `write()` guard
- คงการมองเห็น Ticket ของบริษัทเดียวกันตามกฎเดิม
- คงพฤติกรรมของ Support Agent และ Helpdesk Manager
- เพิ่ม automated tests สำหรับการแก้ไข Draft ของตนเอง การปฏิเสธ Draft ของผู้อื่น และการอ่าน Ticket ของบริษัทเดียวกัน
- ไม่เปลี่ยน Workflow, Approval, SLA, LINE Notification, Attachment Policy หรือข้อมูลเดิมย้อนหลัง
- Local-only: ยังไม่ Deploy, Upgrade หรือ Restart DEV/Production

## DEV Delivery (2026-09-13)

- Uploaded only `buz_it_helpdesk` to DEV with `scp`.
- Upgraded `buz_it_helpdesk` in `MOG_DEV`; Odoo reported the module loaded successfully.
- Restarted the DEV `odoo` container successfully.
- Verified remote manifest version `17.0.1.3.7`, module state `installed`, and HTTP `/web` response `303`.
- Browser UAT was not performed in this delivery.

- Locked policy: one SLA Settings record per company; retained SQL constraint `unique(company_id)`.
- Added timezone validation against `pytz` supported timezones with clear validation errors.
- Added minute-level working-hours validation, including lunch-range validation and safe handling of invalid legacy values.
- Fixed `24:00` handling so the work interval ends at midnight on the following local date.
- Prevented SLA deadline calculation when the active configuration is incomplete or invalid.
- Reused the SLA configuration and closed/pending stage records in the critical ticket computation path.
- Preserved `No SLA`, workflow timestamps, and `Paused` deadline behavior.
- Added targeted SLA tests for timezone, time formats, `24:00`, consecutive holidays, no matching rule, invalid configuration, one-company constraint, workflow timestamps, Paused behavior, role access, and multi-company isolation.
- Static checks passed: Python AST, XML parse, manifest parse, and `git diff --check`.
- Targeted isolated Odoo result: `0 failed, 0 error(s) of 20 tests`.
- Full module suite and Browser UAT remain pending; no DEV deploy, upgrade, or restart was performed for this worklog entry.

- Upload เฉพาะโมดูล `buz_it_helpdesk` ไปยัง DEV สำเร็จด้วย `scp`
- Upgrade `buz_it_helpdesk` บนฐานข้อมูล `MOG_DEV` สำเร็จ และโหลด `helpdesk_ticket_views.xml` สำเร็จ
- Restart container `odoo` สำเร็จ; container status เป็น `Up` และ HTTP health check ได้ `200`
- ไม่ได้ deploy ไป Production และยังไม่ได้ทำ Browser/PDF/accounting UAT

## Attachment Access Restriction (2026-09-13)

- กำหนดให้ Requester เห็นและดาวน์โหลดไฟล์แนบได้เฉพาะ Ticket ที่ตนเองเป็น Requester
- Requester เพิ่มหรือลบไฟล์แนบได้เฉพาะ Draft ของตนเอง; Ticket หลังจากนั้นดู/ดาวน์โหลดได้อย่างเดียว
- เพิ่ม Backend guard ที่ `ir.attachment` และ Ticket เพื่อป้องกัน Preview, Download, ORM/API/RPC และการเปลี่ยนความสัมพันธ์ไฟล์แนบ
- Support Agent และ Helpdesk Manager ใช้สิทธิ์การเข้าถึง Ticket เดิม
- เพิ่ม automated tests สำหรับการอ่าน, เพิ่ม, ลบ, สิทธิ์ข้ามผู้ใช้ และการคงสิทธิ์ของ Support/Manager
- Local-only: ยังไม่ Deploy, Upgrade หรือ Restart DEV/Production
## IT Attachments Feature Parity (2026-09-13)

- กำหนดให้ `it_attachment_ids` รองรับการอัปโหลด ลบ Preview Download และ Paste Screenshot ผ่าน `Ctrl+V` เหมือน `attachment_ids`
- คงฟิลด์และตารางความสัมพันธ์ของไฟล์แนบ User กับทีม IT แยกจากกัน ไม่รวมข้อมูลเข้าหากัน และไม่ทำ Data Backfill
- ปรับ Attachment Widget และ Backend attachment access ให้รองรับทั้งสองความสัมพันธ์ โดยคงสิทธิ์เดิมของ Requester, Support Agent และ Manager
- เพิ่ม Automated Tests สำหรับการแยกความสัมพันธ์ การใช้งานของทีม IT และการป้องกันการจัดการโดยผู้ไม่มีสิทธิ์
- ตรวจสอบใน local isolated test เท่านั้น; ยังไม่มีการ Deploy, Upgrade หรือ Restart Server

## IT Management Dashboard Improvements (2026-09-13)

- ขอบเขตการปรับปรุงครอบคลุม `buz_it_helpdesk` และ `buz_it_asset` โดย Dashboard อยู่ใน `buz_it_asset` และอ่านข้อมูล Ticket/SLA จาก `buz_it_helpdesk`
- เพิ่ม Overdue SLA สำหรับ Response และ Resolution โดยรวม Ticket เดียวกันเป็นรายการเดียว แสดงตาม Timezone ของผู้ใช้ และไม่รวม No SLA, Paused, Resolved, Closed หรือข้อมูลที่ไม่สมบูรณ์
- เพิ่ม Unassigned Tickets, Expired/Overallocated License และหมวด Asset `Uncategorized`
- ปรับ Dashboard และ Drill-down ให้ไม่รวมข้อมูล Archive และเปิดรายการที่เลือกโดยตรง พร้อมรักษาการกรองบริษัทเดิม
- ปรับ Refresh ให้คงข้อมูลเดิมระหว่างโหลด แสดง Last Updated และแจ้งเตือนเมื่อข้อมูลใหม่โหลดไม่สำเร็จ
- คงชื่อ `Open Tickets`, Layout หลัก, สิทธิ์ Dashboard, SLA calculation, Workflow, Approval และ Notification เดิม
- เพิ่ม Dashboard automated tests และตรวจ XML/JavaScript/การโหลด assets; Browser UAT ต้องตรวจ Desktop และหน้าจอแคบแยกต่างหาก
- แก้ User Guide ให้ Requester ใช้ `My Tickets` และไม่เข้าถึง IT Management Dashboard
- Local-only: ยังไม่ Deploy, Upgrade หรือ Restart DEV/Production และไม่ทำ Data Backfill
