# วิธีการทดสอบ VAT Input และ WHT จาก Vendor Bills

## ขั้นตอนที่ 1: สร้าง Vendor Bill สำหรับ Shopee
1. ไปที่ Accounting > Vendors > Bills
2. สร้าง Bill ใหม่
   - Vendor: Shopee (หรือ marketplace partner ที่ใช้)
   - Product Line: Commission Fee - 1,000 บาท
   - Tax: VAT 7% (70 บาท) + WHT 3% (-30 บาท)
   - Total: 1,040 บาท

## ขั้นตอนที่ 2: Post Vendor Bill
1. Confirm และ Post vendor bill
2. ตรวจสอบ Journal Entries ว่ามี tax lines ถูกต้อง

## ขั้นตอนที่ 3: เชื่อมโยง Vendor Bill กับ Settlement
1. เปิด Vendor Bill ที่สร้างแล้ว
2. ใน "Other Info" tab หาฟิลด์ "Linked Settlement" 
3. เลือก Settlement ที่ต้องการเชื่อมโยง

## ขั้นตอนที่ 4: ตรวจสอบการคำนวณ
1. กลับไปที่ Settlement 
2. ไปที่ tab "Linked Vendor Bills" - ควรเห็น Bill ที่เชื่อมโยงแล้ว
3. ไปที่ tab "Fee Allocations" - ควรเห็น VAT และ WHT ถูกคำนวณแล้ว

## สำหรับ Debug
ดู log file: /var/log/odoo/instance1.log
หาข้อความ "=== Computing settlement totals"
