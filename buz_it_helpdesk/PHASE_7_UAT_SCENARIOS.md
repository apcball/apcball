# Phase 7 UAT Scenarios

สถานะเอกสาร: รอผู้ใช้ธุรกิจตรวจรับและลงนาม

เอกสารนี้อยู่ในขอบเขตระยะที่ 7 เท่านั้น ใช้เป็นหลักฐานสำหรับการตรวจรับ

| บทบาท | Scenario | Expected result | Evidence / Sign-off |
|---|---|---|---|
| Requester | สร้าง Ticket, ยืนยัน Ticket และตอบกลับผ่าน Portal | เห็นเฉพาะ Ticket ของตนเอง, ข้อมูลที่ป้อนผ่านการ sanitize และเพิ่ม Attachment ตาม MIME/ขนาดที่อนุญาต | รอผู้ใช้ |
| Agent | รับงาน, เปลี่ยนสถานะ, ตรวจ SLA และเปิด Dashboard | ทำงานได้เฉพาะบริษัทที่เข้าถึงได้, SLA สร้าง Activity ครั้งเดียว และไม่สร้าง Outbound Email | รอผู้ใช้ |
| Manager | ตรวจ Ticket, IT Asset, Renewal และ Dashboard | เห็นข้อมูลตามสิทธิ์ Manager, KPI/Drill-down ตรงกับ Source Records และไม่เห็น Secret | รอผู้ใช้ |
| IT Asset Manager | จัดสรร License Seat, ส่งซ่อม, รับคืน และตรวจ History | ห้ามจัดสรรเกินจำนวน Seat, การเปลี่ยนแปลงมี History และป้องกันการลบข้อมูลสำคัญ | รอผู้ใช้ |

## UAT checklist

- [ ] ทดสอบบทบาท Requester
- [ ] ทดสอบบทบาท Agent
- [ ] ทดสอบบทบาท Manager
- [ ] ทดสอบบทบาท IT Asset Manager
- [ ] ทดสอบ Multi-company และยืนยันว่าไม่มีข้อมูลข้ามบริษัท
- [ ] ทดสอบ Dashboard KPI และ Drill-down กับ Source Records
- [ ] ตรวจ Log, Chatter, Notification, Mail Queue, Export และ Report ว่าไม่มีข้อมูลลับ
- [ ] บันทึก Known Issues ที่เหลือ และยืนยันว่าไม่มีระดับ Critical/High
- [ ] ผู้ใช้ธุรกิจลงนามผล UAT