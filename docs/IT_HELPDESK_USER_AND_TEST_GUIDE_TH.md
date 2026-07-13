# คู่มือการใช้งานและทดสอบระบบ IT Helpdesk

**โมดูล:** buz_it_helpdesk บน Odoo 17  
**ฉบับ:** สำหรับ DEV/UAT  
**ปรับปรุงล่าสุด:** 13 กรกฎาคม 2026

เอกสารนี้ใช้เป็นคู่มือสำหรับ User และเป็น Test Script สำหรับตรวจสอบระบบ IT Helpdesk

## 1. ขอบเขตระบบ

- สร้าง Ticket ผ่าน My Tickets, Portal และ Email Alias
- ใช้ Odoo Chatter สำหรับการตอบกลับ ประวัติ และ Followers
- กำหนด Category, Priority, Team, Agent และ Company
- คำนวณ SLA ตามเวลาทำการและปฏิทินของบริษัท
- หยุด SLA เมื่อสถานะเป็น Pending User และคำนวณต่อเมื่อกลับมาทำงาน
- รองรับไฟล์แนบ Knowledge Base และ Email Threading
- แยกสิทธิ์ตาม Requester, Support Agent และ Helpdesk Manager

## 2. สิทธิ์ผู้ใช้งาน

| กลุ่ม | สิทธิ์ |
|---|---|
| IT Management / Requester | ต้องเป็น Internal User เห็นและสร้าง Ticket ของตนเองเท่านั้น |
| IT Management / Support Agent | ดูและดำเนินการ Ticket ใน Company ที่ได้รับอนุญาต |
| IT Management / Helpdesk Manager | จัดการ Ticket และการตั้งค่าของ Company ที่ได้รับอนุญาต |

User ทั่วไปต้องถูกเพิ่มเข้า Group **IT Management / Requester** การเป็น Internal User เพียงอย่างเดียวไม่เพียงพอ

## 3. เมนูของ Requester

- **Dashboard:** เห็นเฉพาะ Ticket ของตนเอง ไม่มี Create, Edit และ Delete
- **My Tickets:** เห็นเฉพาะ Ticket ของตนเอง และเป็นจุดที่ใช้สร้าง Ticket ใหม่
- **Tickets:** เมนูสำหรับ Agent ไม่แสดงแก่ Requester
- **Knowledge Base:** อ่านบทความที่ได้รับอนุญาต
- **SLA/Settings:** Requester ไม่มีสิทธิ์เข้าถึงข้อมูล SLA และการตั้งค่า

## 4. สร้าง Ticket

1. Login ด้วย User ที่อยู่ใน Group Requester
2. ไปที่ **IT Management > My Tickets**
3. กด **New**
4. กรอก Subject, Description, Category และ Priority
5. แนบภาพหน้าจอหรือไฟล์ที่เกี่ยวข้องได้
6. กด **Save**

Ticket ใหม่จะมีสถานะ **Draft**

ในสถานะ Draft:

- SLA ยังไม่เริ่มคำนวณ
- Requester แก้ไขรายละเอียดและแนบไฟล์ได้
- มีเพียงเจ้าของ Ticket ที่อยู่ใน Group Requester ที่กด Confirm ได้

## 5. Confirm Ticket

1. เปิด Ticket Draft จาก **My Tickets**
2. ตรวจสอบข้อมูลและไฟล์แนบ
3. กดปุ่ม **Confirm**
4. สถานะจะเปลี่ยนจาก **Draft** เป็น **New**
5. SLA จะเริ่มคำนวณตามเวลาทำการของ Company
6. Ticket จะเข้าสู่คิวของ Agent

หลัง Confirm แล้ว Requester จะไม่สามารถแก้ไข Workflow, Team, Agent, SLA, Company และข้อมูลที่ถูกป้องกันได้

## 6. สถานะ Ticket

| สถานะ | ความหมาย |
|---|---|
| Draft | บันทึกแล้ว แต่ยังไม่ได้ Confirm |
| New | Confirm แล้ว รอ Agent รับงาน |
| Assigned | มีการมอบหมาย Agent แล้ว |
| In Progress | Agent กำลังดำเนินการ |
| Pending User | รอข้อมูลจาก User และ SLA หยุดชั่วคราว |
| Resolved | แก้ไขแล้ว รอปิดงาน |
| Closed | ปิด Ticket เรียบร้อย |

## 7. การติดตามและตอบกลับ

- ดูรายละเอียด ประวัติ และไฟล์แนบได้จาก Dashboard หรือ My Tickets
- ใช้ Chatter เพื่อตอบกลับและติดตามประวัติ
- การตอบกลับจาก Agent จะบันทึก First Response
- การตอบ Email ใน Thread เดิมต้องอัปเดต Ticket เดิม ไม่สร้างซ้ำ เมื่อมี Message-ID, In-Reply-To หรือเลข Ticket ใน Subject
- Portal/My Helpdesk ใช้ได้เมื่อ Portal ถูกเปิดใช้งานและ User มีสิทธิ์ Login

## 8. การใช้งาน Email

1. ส่ง Email ไปยัง Email Alias ของ Helpdesk ที่ผู้ดูแลระบบกำหนด
2. ระบุปัญหาใน Subject และ Body พร้อมแนบไฟล์ถ้ามี
3. ระบบจะสร้าง Ticket จาก Email
4. หาก Ticket เป็น Draft ให้ Requester เปิดจาก My Tickets แล้วกด Confirm
5. การตอบกลับต้องใช้ Reply ใน Thread เดิม

Email ของผู้ส่งควรถูกผูกกับ User ใน Odoo เพื่อให้ระบุ Requester และสิทธิ์ได้ถูกต้อง

## 9. ขั้นตอนของ Support Agent

1. เข้า **IT Management > Tickets** หรือ Dashboard
2. เปิด Ticket ที่เป็น New หรือรอการมอบหมาย
3. ตรวจสอบรายละเอียดและไฟล์แนบ
4. กด **Assign to Me**
5. เปลี่ยนเป็น In Progress เมื่อเริ่มทำงาน
6. เปลี่ยนเป็น Pending User เมื่อต้องรอข้อมูล
7. เมื่อได้รับข้อมูล ให้เปลี่ยนออกจาก Pending User
8. ตอบกลับใน Chatter หรือ Email
9. เปลี่ยนเป็น **Resolved** เมื่อแก้ไขเสร็จ
10. กด **Close** หลังตรวจสอบผลแล้ว

ระบบไม่อนุญาตให้ปิด Ticket ที่ยังไม่เป็น Resolved

## 10. SLA

- SLA เริ่มหลัง Confirm และอยู่สถานะ New
- ใช้ Resource Calendar ของ Company
- วันหยุดและเวลานอกทำการไม่ถูกนับเมื่อ Calendar ตั้งค่าไว้
- Pending User หยุด SLA
- เมื่อกลับมาทำงาน Deadline จะถูกเลื่อนตามเวลาทำการ
- Cron ตรวจสอบ Ticket ที่เกิน SLA และแจ้งใน Chatter ให้ทีม/Manager

Requester ไม่จำเป็นต้องเข้าถึงเมนู SLA เพราะระบบคำนวณให้โดยอัตโนมัติ

## 11. Knowledge Base

1. ไปที่ **IT Management > Knowledge Base**
2. ค้นหาบทความตาม Category หรือคำค้น
3. อ่านวิธีแก้ไขปัญหา
4. ให้ Agent เชื่อมบทความกับ Ticket ในช่อง Knowledge Articles Used
5. Agent/Manager สร้างและเผยแพร่บทความได้ตามสิทธิ์

## 12. Test Script สำหรับ UAT

### Requester และสิทธิ์

| ID | ทดสอบ | ผลที่คาดหวัง |
|---|---|---|
| RQ-01 | Login ด้วย Requester | เข้า IT Helpdesk ได้ |
| RQ-02 | เปิด Dashboard | เห็นเฉพาะ Ticket ของตนเอง |
| RQ-03 | ตรวจ Dashboard | ไม่มี Create, Edit, Delete |
| RQ-04 | เปิด My Tickets | เห็นเฉพาะ Ticket ของตนเอง |
| RQ-05 | เปิด Ticket ของ User อื่น | เข้าถึงไม่ได้ |
| RQ-06 | เปิด Tickets/SLA/Settings | ไม่เห็นหรือเข้าถึงไม่ได้ |

### Draft และ Confirm

| ID | ทดสอบ | ผลที่คาดหวัง |
|---|---|---|
| WF-01 | สร้างจาก My Tickets | สร้างได้และเป็น Draft |
| WF-02 | สร้างจาก Dashboard | ไม่มีปุ่ม Create |
| WF-03 | แก้ไขและแนบไฟล์ใน Draft | ทำได้ |
| WF-04 | เปิด Draft ของตนเอง | เห็นปุ่ม Confirm |
| WF-05 | กด Confirm | เปลี่ยนเป็น New |
| WF-06 | ตรวจ SLA หลัง Confirm | คำนวณตาม Company Calendar |
| WF-07 | Confirm Ticket ของ User อื่น | ระบบไม่อนุญาต |
| WF-08 | แก้ข้อมูลสำคัญหลัง Confirm | ระบบไม่อนุญาต |

### Agent, SLA และ Lifecycle

| ID | ทดสอบ | ผลที่คาดหวัง |
|---|---|---|
| AG-01 | Agent เปิด Ticket New | เห็นรายละเอียดและไฟล์แนบ |
| AG-02 | Assign to Me | มี Agent และเป็น Assigned |
| AG-03 | เปลี่ยนเป็น In Progress | เปลี่ยนสำเร็จ |
| AG-04 | เปลี่ยนเป็น Pending User | SLA หยุด |
| AG-05 | เปลี่ยนออกจาก Pending User | SLA คำนวณต่อและเลื่อน Deadline |
| AG-06 | ตอบใน Chatter | บันทึก First Response |
| AG-07 | Resolved แล้ว Close | ปิดได้ตามลำดับ |
| AG-08 | Close ก่อน Resolved | ระบบไม่อนุญาต |

### Email, Portal, Attachment และ Company

| ID | ทดสอบ | ผลที่คาดหวัง |
|---|---|---|
| EM-01 | ส่ง Email ใหม่ไป Alias | สร้าง Ticket ใหม่ |
| EM-02 | Reply Email Thread เดิม | เพิ่มข้อความใน Ticket เดิม ไม่สร้างซ้ำ |
| EM-03 | เปิด Portal/My Helpdesk | เห็นเฉพาะ Ticket ของตนเอง |
| EM-04 | ตอบและแนบไฟล์จาก Portal | เพิ่มใน Ticket เดิมได้ |
| EM-05 | เปิดไฟล์ของ Ticket อื่น | ระบบไม่อนุญาต |
| MC-01 | Agent ดู Company ที่ได้รับอนุญาต | เห็นเฉพาะ Company ที่มีสิทธิ์ |
| MC-02 | ตรวจข้อมูลข้าม Company | ไม่มีข้อมูลรั่วไหล |
| MC-03 | Manager จัดการ Company ของตนเอง | ทำได้ตามสิทธิ์ |

## 13. แบบฟอร์มบันทึกผล UAT

    ผู้ทดสอบ: ______________________________________
    วันที่ทดสอบ: ___________________________________
    User / Group: __________________________________
    Company: ______________________________________
    Test Case ID: __________________________________
    ขั้นตอนที่ทดสอบ: _______________________________
    Expected Result: ________________________________
    Actual Result: __________________________________
    ผลการทดสอบ:  [ ] Pass   [ ] Fail   [ ] Blocked
    Ticket Number / Screenshot: _____________________
    หมายเหตุ: ______________________________________

## 14. การแก้ปัญหาเบื้องต้น

### ไม่เห็นเมนู IT Helpdesk

- ตรวจสอบว่าเป็น Internal User
- ตรวจสอบ Group IT Management / Requester
- ตรวจสอบ Company Access
- Logout/Login ใหม่ หรือ Hard Refresh

### ไม่เห็นปุ่ม Confirm

- Ticket ต้องเป็นของ User ที่ Login อยู่
- Ticket ต้องมีสถานะ Draft
- User ต้องอยู่ใน Group Requester
- เปิด Ticket จาก My Tickets
- Logout/Login ใหม่ หรือ Hard Refresh

### พบ Access Error: Helpdesk Stage หรือ Helpdesk SLA

- ไม่ควรเพิ่มสิทธิ์ SLA ให้ Requester
- ตรวจสอบว่า buz_it_helpdesk เป็นเวอร์ชันล่าสุด
- ตรวจสอบ Group Requester และ Company Access
- บันทึก User, Company, Ticket Number และภาพ Error ส่งผู้ดูแลระบบ

### Email ตอบกลับสร้าง Ticket ซ้ำ

- ใช้ Reply ใน Thread เดิม
- อย่าลบเลข Ticket หรือ Header ของ Email
- ตรวจสอบ Message-ID, In-Reply-To, Email Alias และ Mail Gateway

## 15. เกณฑ์ผ่านก่อนเปิดใช้งานจริง

- Requester สร้าง Ticket ได้เฉพาะจาก My Tickets
- Ticket ใหม่เริ่มเป็น Draft
- เจ้าของ Ticket กด Confirm ได้และสถานะเป็น New
- Dashboard แสดงเฉพาะ Ticket ของตนเองและไม่มี Create/Edit/Delete
- Agent รับและดำเนินการ Ticket ได้
- SLA เริ่มหลัง Confirm และใช้เวลาทำการจริง
- Pending User หยุด SLA และกลับมาคำนวณต่อได้
- Email Reply ไม่สร้าง Ticket ซ้ำ
- Portal และไฟล์แนบไม่เปิดเผยข้อมูลของ User อื่น
- ทดสอบอย่างน้อย 3 บทบาทและ 2 Company
- บันทึกหลักฐานผลการทดสอบทุกกรณี
