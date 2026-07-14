แผนปรับความสมบูรณ์ของ BUZ IT Helpdesk
สรุปผลตรวจ
โครงสร้างโมดูล, manifest, XML และ JavaScript ถูกต้อง แต่ควรเพิ่ม/แก้ 4 จุดก่อนใช้งานจริง:
ไฟล์แนบจากหน้าเว็บถูกสร้างใน ir.attachment แต่ยังไม่เชื่อมกับ ticket.attachment_ids
การเพิ่ม follower และ Activity รองรับเฉพาะตอนสร้าง/ยืนยัน Ticket ไม่ครอบคลุมการมอบหมายภายหลัง
Manager ยังมองไม่เห็น Draft ของผู้อื่น แม้ชื่อ record rule ระบุว่าเข้าถึงทุก Ticket
Tests ยังไม่ครอบคลุม notification ที่เพิ่งแก้, portal attachment, record rules และ multi-company
หน้า /my/helpdesk จะรองรับเฉพาะพนักงานภายในที่มีกลุ่ม Requester ตามที่ยืนยันไว้
การเปลี่ยนแปลงหลัก
เชื่อมไฟล์ที่อัปโหลดผ่านหน้าเว็บเข้ากับ attachment_ids ด้วย fields.Command.link() ทั้งตอนสร้าง Ticket และตอบกลับ
ใช้ข้อจำกัดขนาด request ของเซิร์ฟเวอร์เดิม ไม่เพิ่ม allowlist ประเภทไฟล์เฉพาะโมดูล
เมื่อ assigned_to หรือ assignee_ids เปลี่ยน:เพิ่มผู้รับผิดชอบใหม่เป็น follower
สร้าง “New IT Helpdesk Ticket” Activity ให้ผู้ใช้ใหม่เมื่อ Ticket พ้น Draft แล้ว
ป้องกัน follower และ Activity ซ้ำ
ไม่ลบ follower หรือประวัติ Activity ของผู้รับผิดชอบเดิม

แก้ Manager record rule เป็นเฉพาะเงื่อนไขบริษัท โดยไม่ตัด Draft; Agent ยังคงไม่เห็น Draft ของผู้อื่น
คง route /my/helpdesk และโมเดล requester_id = res.users; ไม่เพิ่มสิทธิ์ให้ external portal users
รักษาการแก้ไขที่ค้างอยู่ใน models/helpdesk_ticket.py และต่อยอดจาก _get_notification_partners() โดยไม่ย้อนการเปลี่ยนแปลงเดิม
Interfaces และความเข้ากันได้
ไม่มี field, model หรือ route ใหม่ และไม่ต้องมี database migration
พฤติกรรม write() ของ Ticket จะเพิ่มการซิงก์ notification เมื่อเปลี่ยนผู้รับผิดชอบ
สิทธิ์ Manager เปลี่ยนให้เห็น Draft ทุก Ticket ภายในบริษัทที่อนุญาต
Portal attachment ที่อัปโหลดใหม่จะแสดงในหน้า Ticket และ backend attachment widget อย่างถูกต้อง
Test Plan
ทดสอบว่า requester, assigned_to และ assignee_ids ถูกเพิ่มเป็น follower ตอนสร้าง Ticket
ทดสอบว่า Confirm สร้าง Activity ให้ team members และ assignees โดยไม่ซ้ำ
ทดสอบการมอบหมายหลัง Confirm ว่า follower และ Activity ของผู้รับผิดชอบใหม่ถูกสร้าง
ทดสอบไฟล์แนบจากทั้ง Create และ Reply route ว่าปรากฏใน attachment_ids
ทดสอบว่า Manager เห็น Draft ของผู้อื่น, Agent ไม่เห็น และทุกกลุ่มถูกจำกัดตาม allowed companies
ทดสอบการส่ง category/priority ที่ไม่ถูกต้องและ Ticket ที่ผู้ใช้ไม่ได้เป็นเจ้าของ
รัน Odoo tests ผ่านฐานข้อมูล isolated เท่านั้น โดยปรับ test command ไปที่ buz_it_helpdesk; ไม่ใช้ MOG_DEV
รัน static validation ซ้ำสำหรับ Python, XML และ JavaScript
สมมติฐาน
หน้าเว็บเป็น employee self-service ไม่ใช่ external customer portal
ผู้รับผิดชอบที่เพิ่มภายหลังต้องได้รับทั้ง follower notification และ Todo Activity
Manager ต้องเห็น Draft ทั้งหมดในบริษัทที่ตนได้รับอนุญาต