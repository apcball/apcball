BUZ IT Management - Phase 1 Helpdesk Spec

## เป้าหมาย

สร้างแอพ Odoo 17 แบบ standalone สำหรับระบบ IT Management โดยเริ่มจากเมนู Helpdesk เป็นแกนหลักของ phase แรก

เป้าหมายของ phase นี้คือให้ได้ระบบรับแจ้งปัญหา, ติดตามงาน, มอบหมายงาน, ปิดงาน, และตั้งค่าพื้นฐานที่จำเป็นต่อการขยายใน phase ถัดไป

## ขอบเขตของ Phase 1

ให้สร้างเฉพาะส่วน Helpdesk ก่อน โดยโฟกัสฟังก์ชันหลักที่ใช้งานได้จริง

### เมนูที่ต้องมี

- Dashboard
- Helpdesk
  - Tickets
  - My Tickets
  - SLA
  - Categories
  - Priorities
  - Stages
  - Knowledge Base
- Settings
  - Categories
  - Priorities
  - Status
  - Email
  - Notifications
  - Roles
  - System Config

## โครงสร้างที่ต้องการ

ให้เริ่มเป็น custom module บน Odoo 17 ที่สามารถต่อยอดเป็นชุดแอพได้ในอนาคต

แนะนำโครงสร้าง logic แบบนี้:

- `buz_it_management` เป็น module แม่
- `buz_it_helpdesk` เป็น module แรกที่ทำจริงใน phase 1
- module อื่น ๆ เช่น Asset Management, Inventory, User Management ค่อยตามมาใน phase ถัดไป

## แนวคิดการออกแบบ

ให้แยกความต่างระหว่าง:

- `Tickets` = งานทั้งหมดที่ระบบรับเข้ามา
- `My Tickets` = งานของผู้ใช้ที่ login อยู่ หรือ ticket ที่ถูก assign ให้เขา
- `Settings` = ข้อมูลตั้งค่ากลางที่ใช้ร่วมกัน

ควรหลีกเลี่ยงการทำเมนูซ้ำซ้อน เช่น `Categories` ในทั้ง Helpdesk และ Settings แบบคนละความหมาย

ถ้าจะทำให้ดี:

- เมนูหลักสำหรับผู้ใช้ = `Helpdesk`
- เมนูตั้งค่า = `Settings`
- เมนูข้อมูล master เช่น Categories, Priorities, Stages ให้เก็บไว้ใน Settings หรือในกลุ่ม Configuration เดียวกันให้ชัดเจน

## ฟีเจอร์หลักที่ควรมีใน Phase 1

### 1. Ticket Management

สร้าง ticket ได้จากหน้าระบบโดยมีข้อมูลขั้นต่ำดังนี้:

- Ticket No
- Subject
- Description
- Requester
- Department
- Category
- Priority
- Stage
- Assigned To
- Created Date
- Due Date
- SLA Deadline
- Tags
- Attachments
- Source
- Company/Branch ถ้ามี

ควรมีการทำงานพื้นฐาน:

- สร้าง ticket
- แก้ไข ticket
- assign ticket
- เปลี่ยน stage
- ปิด ticket
- แนบไฟล์
- ค้นหาและ filter ได้

### 2. My Tickets

เมนูนี้ควรแสดง ticket ที่เกี่ยวข้องกับ user ปัจจุบัน เช่น:

- ticket ที่ user สร้าง
- ticket ที่ถูก assign ให้ user
- ticket ที่ user เป็นผู้ติดตาม

### 3. Stages / Workflow

แนะนำ workflow เริ่มต้น:

- New
- Assigned
- In Progress
- Pending User
- Resolved
- Closed
- Cancelled

ควรสนับสนุนการกำหนดสีหรือสถานะ visual ชัดเจน

### 4. Priority

ควรมี priority มาตรฐาน เช่น:

- Low
- Medium
- High
- Critical

### 5. Categories

ควรใช้สำหรับจัดกลุ่มประเภทปัญหา เช่น:

- Hardware
- Software
- Network
- Account
- Printer
- Access Request
- Other

### 6. SLA เบื้องต้น

Phase 1 ควรมี SLA แบบง่ายก่อน เช่น:

- ตั้งเวลาตอบรับ
- ตั้งเวลาปิดงาน
- ผูก SLA กับ category และ priority

ยังไม่จำเป็นต้องทำ rule engine ซับซ้อนมากในรอบแรก

### 7. Knowledge Base

สร้างฐานความรู้เบื้องต้นเพื่อช่วยลด ticket ซ้ำ

สิ่งที่ควรมี:

- Article title
- Content
- Category
- Published/Unpublished
- Tags

### 8. Dashboard

Dashboard ของ phase 1 ควรแสดงอย่างน้อย:

- จำนวน ticket ทั้งหมด
- ticket ใหม่
- ticket กำลังดำเนินการ
- ticket ปิดแล้ว
- ticket ที่ SLA ใกล้ผิด
- ticket ตาม priority

## โมเดลข้อมูลที่แนะนำ

### Main Models

- `it.helpdesk.ticket`
- `it.helpdesk.stage`
- `it.helpdesk.category`
- `it.helpdesk.priority`
- `it.helpdesk.sla`
- `it.helpdesk.knowledge.article`

### เสริมที่ควรมี

- `it.helpdesk.ticket.message` ถ้าจะเก็บ log ภายใน
- `it.helpdesk.ticket.follower` ถ้าต้องการติดตามงาน

## สิทธิ์การใช้งาน

ควรกำหนด role อย่างน้อย 3 กลุ่ม:

- Requester
- Support Agent
- Helpdesk Manager

สิทธิ์โดยรวม:

- Requester ดูได้เฉพาะ ticket ของตัวเอง
- Support Agent ดูและจัดการ ticket ที่ assign ให้ หรือ ticket ในทีม
- Helpdesk Manager เห็นทั้งหมดและตั้งค่าระบบได้

## ฟังก์ชันที่ควรมีในหน้า ticket

- ปุ่มสร้าง ticket ใหม่
- ปุ่ม assign
- ปุ่มเปลี่ยน stage
- ปุ่ม resolve
- ปุ่ม close
- ปุ่ม reopen
- ปุ่มเพิ่ม internal note
- ปุ่มส่ง reply ให้ requester

## Email และ Notification

Phase 1 ควรมีการแจ้งเตือนพื้นฐาน:

- แจ้งเมื่อสร้าง ticket
- แจ้งเมื่อมีการ assign
- แจ้งเมื่อมีการ reply
- แจ้งเมื่อ ticket เปลี่ยน stage
- แจ้งเมื่อ ticket ใกล้ถึง SLA

## สิ่งที่ยังไม่ต้องทำใน Phase 1

ยังไม่ต้องสร้าง:

- Asset Management
- Inventory
- Purchase Request
- Employee Directory เต็มรูปแบบ
- Advanced report ซับซ้อน
- Automation ข้ามโมดูลที่มากเกินไป
- AI / chatbot

## Acceptance Criteria สำหรับ Phase 1

งานถือว่าสำเร็จเมื่อ:

- เปิดระบบแล้วเห็นเมนู Helpdesk เป็นเมนูแรก
- สร้าง ticket ได้จริง
- assign ticket ได้จริง
- เปลี่ยน stage ได้จริง
- ดู `My Tickets` ได้
- ตั้งค่า Categories, Priorities, Stages ได้
- มี SLA เบื้องต้น
- มี Knowledge Base เบื้องต้น
- Dashboard แสดงข้อมูลสำคัญได้

## ข้อแนะนำในการพัฒนา

- ทำโครง module ให้สะอาดและต่อยอดง่าย
- แยก master data ออกจาก transaction data
- อย่าผูก logic ทุกอย่างไว้ใน model เดียว
- เริ่มจากความเรียบง่ายก่อน แล้วค่อยเพิ่ม automation ใน phase ถัดไป