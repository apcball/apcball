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

## ขอบเขต Phase 2: Workflow Helpdesk แบบง่าย

Workflow หลัก:

`Draft → New → In Progress → Closed`

เป้าหมายของ Phase 2 คือให้ User เปิด Ticket ได้โดยไม่ต้องเลือก `Team` หรือ
`Assigned To` และให้ระบบส่งงานไปยังทีม IT กลางโดยอัตโนมัติ เมื่อ IT รับงาน
จึงค่อยเติมข้อมูลผู้รับผิดชอบและทีม จากนั้น IT ปิดงานและแจ้งกลับ User

### Phase 2.1: กำหนด Workflow และทีมรับงานกลาง

- กำหนด Stage หลักและ transition ที่อนุญาตสำหรับ `Draft`, `New`,
  `In Progress` และ `Closed`
- เพิ่มแนวคิด `Default Intake Team` สำหรับรับ Ticket ใหม่
- ระบุแผนฟิลด์ `buz.helpdesk.team.is_default_intake`
- ระบุแผนฟิลด์ภายใน `buz.helpdesk.ticket.routing_team_id`
- กำหนดให้มี Default Intake Team ที่ใช้งานอยู่ได้เพียงหนึ่งทีม
- Default Intake Team ต้องมีสมาชิก Active อย่างน้อยหนึ่งคน
- User ต้องสามารถส่ง Ticket ได้โดยไม่ต้องเลือก Team

เกณฑ์ตรวจรับ: ระบบระบุทีมปลายทางได้จาก Default Intake Team โดย User ไม่ต้อง
เลือก Team หรือ Assigned To

### Phase 2.2: ลดความซับซ้อนของฟอร์ม User

- ซ่อน `Team` และ `Assigned To` ขณะ Ticket อยู่สถานะ Draft และ New
- ให้ User กรอกเฉพาะ Subject, Category, Type, Priority, Description และ
  Attachment
- ให้ `Create Ticket` เปลี่ยนสถานะจาก Draft เป็น New
- บันทึกทีมปลายทางไว้ใน `routing_team_id` โดยไม่แสดงเป็นข้อมูลที่ User ต้องกรอก
- หลัง IT รับงานแล้วจึงแสดง Team และ Assigned To แบบอ่านอย่างเดียว

เกณฑ์ตรวจรับ: User สร้างและส่ง Ticket ได้โดยไม่เห็นหรือเลือก Team และ Assigned
To

### Phase 2.3: แจ้ง Activity ไปยังทีม IT

- สร้าง To Do Activity ให้สมาชิก Active ทุกคนใน Default Intake Team
- ป้องกัน Activity ซ้ำเมื่อ action ถูกเรียกซ้ำหรือเกิด transaction retry
- หากไม่มี Default Intake Team หรือไม่มีสมาชิก Active ให้หยุดการส่ง Ticket
  พร้อมข้อความที่เข้าใจง่าย
- User ผู้เปิด Ticket ไม่ต้องได้รับ Activity แจ้งงานใหม่ของทีม IT

เกณฑ์ตรวจรับ: สมาชิกทีม IT ได้รับ Activity คนละหนึ่งรายการ และไม่มีรายการซ้ำ
จากการเรียก action ซ้ำ

### Phase 2.4: IT รับ Ticket

- เพิ่มหรือปรับ `action_receive_ticket()` ให้ใช้ได้เฉพาะสมาชิกทีมปลายทางหรือ
  Helpdesk Manager
- รับได้เฉพาะ Ticket สถานะ New ที่ยังไม่มีผู้รับผิดชอบ
- เติม Team จาก `routing_team_id`
- เติม Assigned To เป็นผู้ที่กดรับงาน
- เปลี่ยนสถานะจาก New เป็น In Progress
- ปิด Activity งานใหม่ของสมาชิกทุกคนหลังมีผู้รับงาน
- ป้องกัน IT สองคนรับ Ticket เดียวกันพร้อมกัน

เกณฑ์ตรวจรับ: ผู้รับคนแรกได้งานและข้อมูล Team/Assigned To ถูกเติม ส่วนผู้รับ
คนถัดไปได้รับข้อความว่า Ticket ถูกรับแล้ว

### Phase 2.5: ปิดงานและแจ้งกลับ User

- เพิ่ม `action_close_ticket()` สำหรับปิดงาน
- อนุญาตให้ผู้รับผิดชอบหรือ Helpdesk Manager ปิด Ticket จาก In Progress เป็น
  Closed
- แจ้ง Requester ผ่าน Odoo Inbox
- บันทึกข้อความการปิดงานใน Chatter
- ไม่สร้าง Activity ค้างให้ User เมื่อปิดงาน

เกณฑ์ตรวจรับ: User เห็นผู้ดำเนินการ สถานะ Closed และข้อความแจ้งปิดงานใน
Chatter พร้อมได้รับ Inbox notification

### Phase 2.6: Security, Validation และ UAT

- บังคับ transition และสิทธิ์ที่ฝั่ง Backend ไม่พึ่งเฉพาะการซ่อนปุ่มใน View
- ป้องกันการกำหนด Team, Assigned To หรือ Stage โดยตรงผ่าน RPC หรือ import
- ตรวจสิทธิ์ของ Requester, Support Agent และ Helpdesk Manager สำหรับทุก action
- จัดทำ UAT สำหรับ User, IT อย่างน้อยสองคน และ Manager
- ตรวจกรณีไม่มี Default Intake Team หรือไม่มีสมาชิก Active
- ตรวจกรณี IT สองคนกดรับ Ticket เดียวกัน
- ตรวจกรณีผู้ไม่มีสิทธิ์พยายามรับหรือปิดงาน
- ตรวจ Markdown, UTF-8, heading hierarchy และ `git diff --check`
- ไม่เพิ่ม automated test files และไม่ Deploy DEV ในขั้นเอกสารนี้

เกณฑ์ตรวจรับ: workflow และ security boundary ทำงานตามแผนทั้งผ่าน UI และการ
เรียก Backend โดยตรง

## Interfaces ที่ต้องระบุในแผน

- `buz.helpdesk.team.is_default_intake`
- `buz.helpdesk.ticket.routing_team_id`
- `action_create_ticket()`
- `action_receive_ticket()`
- `action_close_ticket()`
- computed visibility สำหรับปุ่มและฟิลด์ โดย Backend ตรวจสิทธิ์ซ้ำเสมอ

## ขอบเขตและสมมติฐาน

- Phase 2 เดิมถูกแทนที่ทั้งหมดเพื่อไม่ให้แผนซ้ำหรือขัดกัน
- ไม่รวม Pending User, SLA, Cancelled, Resolved, Auto-close, Email template
  และการยืนยันปิดโดย User
- เก็บ Stage Resolved เดิมในระบบแบบปิดการใช้งานเพื่อรักษา XML ID และข้อมูล
  อ้างอิง
- แบ่งการลงมือทำตาม Phase 2.1–2.6 ทีละระยะ และหยุดตรวจรับก่อนเริ่มระยะถัดไป