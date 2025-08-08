# การทดสอบ WHT Tax ใน Odoo - คำแนะนำภาษาไทย

## ขั้นตอนการทดสอบ WHT Tax

### 1. ทดสอบสร้าง Vendor Bill พร้อม WHT

#### Step 1.1: สร้าง Vendor (ผู้ขาย)
```
1. ไปที่ Purchases → Vendors
2. สร้าง Vendor ใหม่:
   - Name: "บริษัท ABC จำกัด"
   - Is a Company: เช็ค
   - Tax ID: "1234567890123" (13 หลัก)
   - Address: ใส่ที่อยู่
```

#### Step 1.2: สร้าง Product พร้อม WHT
```
1. ไปที่ Products → Products
2. สร้าง Product ใหม่:
   - Name: "ค่าบริการ Consulting"
   - Product Type: Service
   - Can be Purchased: เช็ค
   
3. ใน Purchase tab:
   - Supplier Company WHT Tax: เลือก "Service WHT 3%"
   - Cost: 10,000
```

#### Step 1.3: สร้าง Vendor Bill
```
1. ไปที่ Purchases → Bills
2. คลิก Create
3. เลือก Vendor: "บริษัท ABC จำกัด"
4. เพิ่ม Product line:
   - Product: "ค่าบริการ Consulting"
   - Quantity: 1
   - Unit Price: 10,000
   
5. ตรวจสอบ:
   ✅ WHT Tax field ควรแสดง "Service WHT 3%"
   ✅ WHT Amount ควรคำนวณเป็น 300 บาท
   ✅ Total ยังคงเป็น 10,000 บาท
   
6. คลิก Confirm
```

### 2. ทดสอบการจ่ายเงินพร้อมหัก WHT

#### Step 2.1: Register Payment
```
1. ใน Vendor Bill ที่ Confirm แล้ว คลิก "Register Payment"
2. ตรวจสอบ Payment Register Wizard:
   ✅ Amount to Pay ควรแสดง 9,700 บาท (10,000 - 300)
   ✅ Payment Difference Handling: "Keep open"
   ✅ Writeoff Account: ควรเป็น WHT Payable Account
   ✅ Writeoff Label: "Service WHT 3%"
   
3. คลิก "Create Payment"
```

#### Step 2.2: ตรวจสอบ Journal Entries
```
1. ไปที่ Payment record
2. คลิก "Journal Entries" button
3. ตรวจสอบ Journal Entry:

Dr. Accounts Payable        10,000.00
    Cr. Bank Account                  9,700.00
    Cr. WHT Payable (2131)              300.00
```

### 3. ทดสอบการสร้าง WHT Certificate

#### Step 3.1: สร้าง Certificate จาก Payment
```
1. ใน Payment record คลิก "Create WHT Cert"
2. ใส่ข้อมูล:
   - Certificate Number: "WHT2024001"
   - Certificate Date: วันที่ปัจจุบัน
   - Tax Invoice Number: "INV001"
   - Tax Invoice Date: วันที่ Invoice
   
3. คลิก Save
4. คลิก Print เพื่อพิมพ์ใบรับรองฯ
```

#### Step 3.2: ตรวจสอบ Certificate
```
1. ไปที่ Accounting → Withholding Tax → WHT Certificates
2. หา Certificate ที่สร้าง
3. ตรวจสอบข้อมูล:
   ✅ Partner: บริษัท ABC จำกัด
   ✅ Income Amount: 10,000.00
   ✅ WHT Amount: 300.00
   ✅ Tax Rate: 3%
   ✅ Status: Draft/Done
```

### 4. ตรวจสอบ Account Balance

#### Step 4.1: ดู WHT Payable Account
```
1. ไปที่ Accounting → Chart of Accounts
2. หา Account "WHT Payable (2131)"
3. ตรวจสอบ:
   ✅ Credit Balance: 300.00 บาท
   ✅ Account Type: Current Liabilities
   ✅ WHT Account: เช็คอยู่
```

#### Step 4.2: ดู Vendor Balance
```
1. ไปที่ Purchases → Vendors
2. เลือก "บริษัท ABC จำกัด"
3. ตรวจสอบ:
   ✅ Total Payable: 0.00 (จ่ายครบแล้ว)
   ✅ Bills: 1 bill (Paid)
```

## การทดสอบกรณีต่างๆ

### กรณีที่ 1: ค่าเช่า WHT 5%
```
Product: "ค่าเช่าสำนักงาน"
Amount: 20,000 บาท
WHT: 5% = 1,000 บาท
จ่ายจริง: 19,000 บาท
```

### กรณีที่ 2: Personal Income Tax
```
Product: "เงินเดือนพนักงาน"
Amount: 15,000 บาท
PIT: ตามอัตราภาษีเงินได้
จ่ายจริง: 15,000 - PIT amount
```

### กรณีที่ 3: หลาย Invoice รวมกัน
```
1. สร้าง Invoice หลายใบ สำหรับ vendor เดียวกัน
2. เลือกหลาย Invoice ใน Payment Register
3. เช็ค "Group Payments"
4. ระบบจะรวม WHT จากทุก Invoice
```

## Troubleshooting การทดสอบ

### ปัญหา: WHT field ไม่แสดงใน Invoice line
**แก้ไข**:
1. ตรวจสอบ Product มี WHT Tax ตั้งค่าไว้หรือไม่
2. ตรวจสอบ User มี Permission เข้าถึง Accounting Features

### ปัญหา: Payment ไม่หัก WHT อัตโนมัติ
**แก้ไข**:
1. เช็ค "Group Payment" ใน Payment Register
2. ตรวจสอบ WHT Tax มี Account ตั้งค่าถูกต้อง
3. ตรวจสอบ Invoice line มี WHT Tax

### ปัญหา: ไม่สามารถสร้าง WHT Certificate
**แก้ไข**:
1. ตรวจสอบ Payment status = Posted
2. ตรวจสอบ Payment มี WHT amount > 0
3. ตรวจสอบ Partner มี Tax ID

### ปัญหา: Journal Entry ไม่ถูกต้อง
**แก้ไข**:
1. ตรวจสอบ WHT Account configuration
2. ตรวจสอบ WHT Tax มี Account ที่ถูกต้อง
3. ลอง Reconcile Payment manually

## Checklist การทดสอบที่สมบูรณ์

- [ ] WHT Account สร้างและตั้งค่าถูกต้อง
- [ ] WHT Tax Types สร้างครบ พร้อม Account
- [ ] Product ตั้งค่า WHT Tax ถูกต้อง
- [ ] สร้าง Vendor Bill ได้ มี WHT calculation
- [ ] Register Payment หัก WHT อัตโนมัติ
- [ ] Journal Entry ถูกต้อง
- [ ] สร้าง WHT Certificate ได้
- [ ] Account Balance ถูกต้อง
- [ ] Print Certificate ได้

เมื่อผ่านการทดสอบทุกขั้นตอนแล้ว แสดงว่า WHT Tax ใน Odoo พร้อมใช้งานจริงแล้วครับ!
