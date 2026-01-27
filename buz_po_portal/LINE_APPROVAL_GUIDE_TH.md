# คู่มือการใช้งาน LINE Approval สำหรับ Purchase Order

## ภาพรวม

ระบบนี้ช่วยให้สามารถส่ง link อนุมัติ Purchase Order ผ่าน LINE ไปยังผู้อนุมัติได้โดยตรง พร้อม portal สำหรับการอนุมัติบนมือถือ

## ขั้นตอนการตั้งค่า

### 1. ตั้งค่า LINE Official Account

1. สร้าง LINE Official Account ที่ https://developers.line.biz/
2. สร้าง Messaging API channel
3. คัดลอก Channel Access Token และ Channel Secret
4. ใน Odoo ไปที่ **การตั้งค่า > การตั้งค่าทั่วไป > LINE Notification**
5. กรอก Channel Access Token และ Channel Secret

### 2. ตั้งค่า LINE User ID สำหรับผู้อนุมัติ

สำหรับทุกคนที่จะเป็นผู้อนุมัติ:

1. ไปที่ **การตั้งค่า > ผู้ใช้**
2. เลือกผู้ใช้ที่ต้องการ
3. ในหัวข้อ "LINE Notification" ให้กรอก LINE User ID
4. วิธีหา LINE User ID:
   - เพิ่ม Official Account ที่สร้างไว้เป็นเพื่อน
   - ส่งข้อความใดก็ได้ไปที่ Official Account
   - ดู webhook event เพื่อหา User ID

### 3. กำหนดสิทธิ์

1. ไปที่ **การตั้งค่า > ผู้ใช้และบริษัท > กลุ่ม**
2. เพิ่มผู้ใช้ที่จะส่ง LINE notification เข้ากลุ่ม "LINE Notification User"

## วิธีการใช้งาน

### สำหรับผู้สร้าง PO

1. **สร้างและส่ง PO เพื่อตรวจสอบ**
   - สร้าง Purchase Order ตามปกติ
   - กรอกข้อมูลให้ครบถ้วน
   - คลิกปุ่ม **"Send for Review"**
   - เลือกผู้ตรวจสอบ (Reviewer)
   - ระบบจะเปลี่ยนสถานะเป็น "Waiting for Review"

2. **ส่ง LINE ให้ผู้ตรวจสอบ**
   - คลิกปุ่ม **"Send LINE Approval Request"** (สีฟ้า)
   - ระบบจะส่ง LINE message พร้อม link อนุมัติไปให้ผู้ตรวจสอบ
   - ผู้ตรวจสอบจะได้รับ LINE ทันที

3. **หลังผู้ตรวจสอบอนุมัติ**
   - ระบบจะเปลี่ยนสถานะเป็น "Waiting for Approval"
   - คลิกปุ่ม **"Send LINE Approval Request"** อีกครั้ง
   - ระบบจะส่ง LINE ไปให้ผู้อนุมัติ (Manager)

4. **หลังผู้อนุมัติอนุมัติ**
   - ระบบจะเปลี่ยนสถานะเป็น "Approved"
   - สามารถ Confirm PO ได้

### สำหรับผู้ตรวจสอบ/ผู้อนุมัติ

1. **รับ LINE notification**
   - จะได้รับข้อความ LINE ที่มีรายละเอียด PO
   - มี link สำหรับอนุมัติ

2. **คลิก link ใน LINE**
   - หน้าจอ portal จะเปิดขึ้นบนมือถือ
   - แสดงรายละเอียด PO ครบถ้วน

3. **ตรวจสอบและอนุมัติ**
   - อ่านรายละเอียด PO
   - คลิก **"อนุมัติ"** หรือ **"ปฏิเสธ"**
   - สามารถใส่ comment เพิ่มเติมได้
   - คลิก **"ส่ง"**

4. **ระบบจะอัปเดตอัตโนมัติ**
   - สถานะ PO จะเปลี่ยนทันที
   - Link จะหมดอายุไม่สามารถใช้ซ้ำได้
   - มีการบันทึก audit trail ทั้งหมด

## รูปแบบข้อความ LINE

```
📋 Purchase Order Review Required

PO Number: PO00123
Vendor: บริษัท ABC จำกัด
Amount: 125,000.00 THB
Date: 24/01/2026

👉 Review & approve:
https://yourdomain.com/portal/approve/xxx

⚠️ This link will expire in 24 hours
```

## ฟีเจอร์พิเศษ

### 1. ความปลอดภัย
- **Token ปลอดภัย**: ใช้ cryptographic token ที่มีความปลอดภัยสูง
- **ใช้ครั้งเดียว**: หลังอนุมัติหรือปฏิเสธแล้ว link จะใช้ไม่ได้อีก
- **มีกำหนดเวลา**: Link หมดอายุใน 24 ชั่วโมง (ปรับได้)

### 2. การติดตาม
- **Audit Log**: บันทึกการส่ง LINE และการอนุมัติทั้งหมด
- **Chatter**: แสดงประวัติการอนุมัติใน PO
- **Notification Status**: แสดงสถานะการส่ง LINE ใน PO

### 3. รองรับหลายขั้นตอน
- ส่งให้ผู้ตรวจสอบ (Reviewer)
- ส่งให้ผู้อนุมัติ (Manager)
- ใช้ token แยกกันสำหรับแต่ละขั้นตอน

## การแก้ไขปัญหา

### ไม่เห็นปุ่ม "Send LINE Approval Request"

**สาเหตุ:**
- สถานะ PO ไม่ใช่ "Waiting for Review" หรือ "Waiting for Approval"
- ไม่มีสิทธิ์ "LINE Notification User"

**วิธีแก้:**
- ตรวจสอบสถานะ PO
- ติดต่อ admin เพื่อขอสิทธิ์

### ข้อผิดพลาด "No approver defined"

**สาเหตุ:**
- ไม่ได้กำหนดผู้ตรวจสอบหรือผู้อนุมัติใน PO

**วิธีแก้:**
- กรอก Reviewer หรือ Approver ก่อนส่ง LINE

### ข้อผิดพลาด "Approver does not have LINE User ID"

**สาเหตุ:**
- ผู้อนุมัติยังไม่ได้ตั้งค่า LINE User ID

**วิธีแก้:**
- ไปที่การตั้งค่าผู้ใช้
- กรอก LINE User ID ให้ผู้อนุมัติ

### ไม่ได้รับ LINE

**สาเหตุที่เป็นไปได้:**
- LINE credentials ไม่ถูกต้อง
- LINE User ID ผิด
- ไม่มีอินเทอร์เน็ต
- ยังไม่ได้เพิ่ม Official Account เป็นเพื่อน

**วิธีแก้:**
- ตรวจสอบการตั้งค่า LINE
- ตรวจสอบ LINE User ID
- ดู Audit Log เพื่อหา error

### Link หมดอายุ

**วิธีแก้:**
- คลิก "Send LINE Approval Request" ใหม่
- ระบบจะสร้าง token ใหม่
- Token เก่าจะถูกยกเลิก

## ตัวอย่างการใช้งาน

### กรณีปกติ

1. สร้าง PO มูลค่า 50,000 บาท
2. คลิก "Send for Review" → เลือก Reviewer
3. คลิก "Send LINE Approval Request"
4. Reviewer ได้รับ LINE → คลิก link → อนุมัติ
5. PO เปลี่ยนเป็น "Waiting for Approval"
6. คลิก "Send LINE Approval Request" อีกครั้ง
7. Manager ได้รับ LINE → คลิก link → อนุมัติ
8. PO เปลี่ยนเป็น "Approved"
9. Confirm PO ได้

### กรณีปฏิเสธ

1. Reviewer/Manager คลิก link ใน LINE
2. เลือก "ปฏิเสธ"
3. กรอกเหตุผล
4. คลิก "ส่ง"
5. PO เปลี่ยนเป็น "Rejected"
6. ผู้สร้าง PO สามารถแก้ไขและส่งใหม่ได้

## เคล็ดลับ

1. **ตั้งค่า LINE User ID ล่วงหน้า**: เตรียม LINE User ID ของผู้อนุมัติทุกคนไว้ก่อน
2. **ทดสอบก่อนใช้งานจริง**: ลองส่ง test PO เพื่อทดสอบระบบ
3. **ตั้งค่า Mobile Portal**: ให้แน่ใจว่า web.base.url ตั้งค่าถูกต้อง
4. **ตรวจสอบ Audit Log เป็นประจำ**: เพื่อดูประวัติการใช้งาน
5. **กำหนดเวลาหมดอายุที่เหมาะสม**: ปรับเวลาหมดอายุตามความเหมาะสม (default 24 ชม.)

## การปรับแต่งขั้นสูง

### เปลี่ยนรูปแบบข้อความ

สามารถแก้ไขรูปแบบข้อความ LINE ได้ที่ไฟล์ `purchase_order.py` ในฟังก์ชัน `_get_line_approval_message()`

### เปลี่ยนเวลาหมดอายุ token

ไปที่ **การตั้งค่า > การตั้งค่าทั่วไป > LINE Notification** และแก้ไข "Token Expiry (hours)"

### กำหนดผู้อนุมัติอัตโนมัติ

สามารถเขียน logic เพิ่มเติมใน `_get_line_approval_approver()` เพื่อเลือกผู้อนุมัติอัตโนมัติตามเงื่อนไข เช่น ตามยอดเงิน แผนก ฯลฯ

## สรุป

ระบบ LINE Approval ช่วยให้:
- ✅ อนุมัติ PO ได้สะดวกผ่านมือถือ
- ✅ ลดเวลาในการรออนุมัติ
- ✅ มีการบันทึกประวัติครบถ้วน
- ✅ ปลอดภัยด้วย token system
- ✅ รองรับการทำงานแบบ remote

หากมีข้อสงสัยหรือพบปัญหา กรุณาติดต่อผู้ดูแลระบบ
