# WHT Tax และ WHT Certificates Workflow ใน Odoo

## เมื่อไหร่ที่ WHT Tax จะเกิดขึ้น

### 1. การสร้าง Vendor Bill (ใบแจ้งหนี้จากผู้ขาย)
- **WHT Tax จะคำนวณทันที** เมื่อเพิ่มสินค้า/บริการที่มี WHT Tax
- **ระบบจะแสดง WHT amount** ในแต่ละรายการสินค้า
- **WHT Tax ยังไม่ได้ถูกหัก** เงินจริง ณ จุดนี้

```
ตัวอย่าง:
- ค่าบริการ: 10,000 บาท
- WHT 3%: 300 บาท (แสดงใน invoice line)
- ยอดที่ต้องจ่าย: ยังคงเป็น 10,000 บาท
```

### 2. การ Register Payment (จ่ายเงิน)
- **WHT Tax จะถูกหักจริง** เมื่อทำการจ่ายเงิน
- **ระบบจะลดยอดจ่าย** โดยอัตโนมัติ
- **สร้าง Journal Entry** สำหรับ WHT Payable

```
ตัวอย่าง:
- ยอดที่ต้องจ่าย: 10,000 บาท
- WHT หัก: 300 บาท
- จ่ายจริง: 9,700 บาท
- WHT Payable: 300 บาท (เป็นหนี้ต่อกรมสรรพากร)
```

## เมื่อไหร่ต้องสร้าง WHT Certificates

### 1. สร้างทันทีหลังจ่ายเงิน (แนะนำ)
```
1. ไปที่ Payment ที่ได้จ่ายแล้ว
2. คลิก "Create WHT Certificate" button
3. ใส่ข้อมูลเพิ่มเติม:
   - Tax Invoice Number
   - Tax Invoice Date
   - Supplier Tax ID
4. Save และ Print ใบ Certificate
```

### 2. สร้างแบบ Batch (รายเดือน)
```
1. ไปที่ Accounting > Withholding Tax > WHT Certificates
2. คลิก Create
3. เลือกช่วงวันที่
4. เลือก Partner/Vendor
5. ระบบจะรวม WHT จากหลาย Payment
```

## WHT Tax Workflow แบบละเอียด

### ขั้นตอนที่ 1: ตั้งค่าเริ่มต้น
```
✅ สร้าง WHT Account (Current Liabilities)
✅ สร้าง WHT Tax Types (Service 3%, Rent 5%, etc.)
✅ กำหนด WHT Tax ให้กับ Products
✅ ตั้งค่า Partner (Vendor) Tax ID
```

### ขั้นตอนที่ 2: สร้าง Vendor Bill
```
1. สร้าง Vendor Bill
2. เพิ่มสินค้า/บริการที่มี WHT Tax
3. ระบบคำนวณ WHT amount อัตโนมัติ
4. Confirm Bill
```

**Journal Entry ที่เกิดขึ้น:**
```
Dr. Expense Account         10,000
    Cr. Accounts Payable            10,000
```

### ขั้นตอนที่ 3: Register Payment
```
1. คลิก "Register Payment" บน Bill
2. ระบบจะแสดง:
   - Payment Amount: 9,700 (หัก WHT แล้ว)
   - Writeoff Amount: 300 (WHT)
   - Writeoff Account: WHT Payable Account
3. Confirm Payment
```

**Journal Entry ที่เกิดขึ้น:**
```
Dr. Accounts Payable        10,000
    Cr. Bank Account                9,700
    Cr. WHT Payable                   300
```

### ขั้นตอนที่ 4: สร้าง WHT Certificate
```
1. ไปที่ Payment record
2. คลิก "Create WHT Certificate"
3. ใส่ข้อมูล:
   - Certificate Number
   - Certificate Date
   - Income Type
   - Tax Rate
4. Print Certificate
```

## ตัวอย่างการทำงานจริง

### ตัวอย่างที่ 1: ค่าบริการ Consulting
```
1. สร้าง Vendor Bill:
   - ค่าบริการ: 50,000 บาท
   - WHT 3%: 1,500 บาท (คำนวณอัตโนมัติ)

2. Register Payment:
   - จ่ายจริง: 48,500 บาท
   - WHT หัก: 1,500 บาท

3. Create WHT Certificate:
   - Income Type: Professional Service
   - Tax Rate: 3%
   - Amount: 1,500 บาท
```

### ตัวอย่างที่ 2: ค่าเช่า
```
1. สร้าง Vendor Bill:
   - ค่าเช่า: 20,000 บาท
   - WHT 5%: 1,000 บาท

2. Register Payment:
   - จ่ายจริง: 19,000 บาท
   - WHT หัก: 1,000 บาท

3. Create WHT Certificate:
   - Income Type: Rental
   - Tax Rate: 5%
   - Amount: 1,000 บาท
```

## การติดตามและรายงาน

### 1. ดู WHT Payable Balance
```
ไปที่: Accounting > Chart of Accounts
ดู Account: WHT Payable (2131)
Balance = ยอด WHT ที่ต้องนำส่งกรมสรรพากร
```

### 2. รายงาน WHT Certificate
```
ไปที่: Accounting > Withholding Tax > WHT Certificates
Filter ตามเดือน/ปี สำหรับจัดทำรายงาน
```

### 3. การนำส่งภาษี
```
เมื่อนำส่งภาษีแล้ว ให้สร้าง Journal Entry:
Dr. WHT Payable             X,XXX
    Cr. Bank Account                X,XXX
```

## ข้อควรระวัง

### 1. Timing ของการสร้าง Certificate
- **ทำทันที**: หลังจ่ายเงินแต่ละครั้ง (แนะนำ)
- **ทำรวม**: ท้ายเดือน (สำหรับ vendor เดียวกัน)

### 2. ข้อมูลที่ต้องครบถ้วน
- Partner Tax ID
- Invoice Number และ Date
- WHT Rate และ Amount ถูกต้อง

### 3. การแก้ไข
- หาก Certificate ผิด ต้อง Cancel และสร้างใหม่
- อย่าลืม Reverse Journal Entry ด้วย

## สรุป Timeline

```
Day 1: สร้าง Vendor Bill → WHT คำนวณแต่ยังไม่หัก
Day 7: จ่ายเงิน → WHT ถูกหักจริง + สร้าง Payable
Day 7: สร้าง WHT Certificate → ออกใบรับรอง
Day 15: รายงานต่อกรมสรรพากร (ภายใน 15 วันของเดือนถัดไป)
```

ระบบ WHT ใน Odoo จะทำงานแบบนี้ครับ - สำคัญที่การตั้งค่าให้ถูกต้องตั้งแต่แรก!
