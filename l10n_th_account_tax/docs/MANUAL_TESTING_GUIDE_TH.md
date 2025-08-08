# คู่มือทดสอบ WHT Auto Fill (ภาษาไทย)

## วิธีทดสอบ WHT Auto Fill แบบ Manual

### ขั้นตอนที่ 1: ตรวจสอบการตั้งค่าพื้นฐาน

1. **ตรวจสอบ WHT Tax Types**
   ```
   Accounting → Configuration → WHT Configuration → WHT Tax Types
   ```
   - ต้องมี Service WHT 3% และ Rental WHT 5%
   - แต่ละ WHT Tax ต้องมี Account กำหนดไว้

2. **ตรวจสอบ WHT Accounts**
   ```
   Accounting → Configuration → Chart of Accounts
   ```
   - ต้องมี Account ประเภท WHT (เช่น WHT Payable, WHT Service, WHT Rental)
   - Account ต้องมีช่อง "WHT Account" เป็น True

### ขั้นตอนที่ 2: ตั้งค่า Product

1. **เข้าไปที่ Product**
   ```
   Inventory → Master Data → Products
   ```

2. **เลือก Product ประเภท Service**

3. **ตั้งค่า WHT Tab**
   - Supplier Company WHT Tax: เลือก Service WHT 3%
   - Supplier Individual WHT Tax: เลือก Service WHT 3%

### ขั้นตอนที่ 3: สร้าง Vendor Invoice

1. **สร้าง Invoice**
   ```
   Accounting → Vendors → Bills
   ```

2. **กรอกข้อมูล**
   - Vendor: เลือก Vendor ใดก็ได้
   - Product: เลือก Product ที่ตั้งค่า WHT แล้ว
   - Quantity: 1
   - Price: 10,000 บาท

3. **ตรวจสอบ Invoice Lines**
   - คลิกที่ Invoice Line แล้วดู Journal Items
   - ต้องพบ WHT Tax Field มีค่า

4. **Confirm Invoice**

### ขั้นตอนที่ 4: ทดสอบ Payment Register

1. **เข้าไปที่ Payment Register**
   - จาก Invoice กด "Register Payment"

2. **ตรวจสอบ Auto Fill**
   ```
   ที่ควรจะเห็น:
   - Payment Amount: 9,700 บาท (10,000 - 300 WHT)
   - WHT Tax: Service WHT 3%
   - WHT Amount Base: 10,000 บาท
   - Payment Difference Handling: "Keep open"
   - Writeoff Account: WHT Service Account
   ```

3. **ถ้า Auto Fill ไม่ทำงาน**
   - Payment Amount จะยังเป็น 10,000 บาท
   - WHT fields จะว่าง

### ขั้นตอนที่ 5: สร้าง Payment

1. **กด Create Payment**

2. **ตรวจสอบ Journal Entry**
   ```
   Payment Journal Entry ควรมี:
   - Dr. Payable Account: 10,000
   - Cr. Bank Account: 9,700
   - Cr. WHT Service Account: 300
   ```

## การแก้ไขปัญหา

### ปัญหา: WHT ไม่ Auto Fill

**สาเหตุที่เป็นไปได้:**

1. **Product ไม่มี WHT Tax**
   ```
   แก้ไข: ไปตั้งค่า WHT Tax ใน Product → Accounting Tab
   ```

2. **Invoice Line ไม่มี WHT Tax**
   ```
   แก้ไข: Edit Invoice Line → กำหนด WHT Tax manually
   ```

3. **WHT Account ไม่ถูกต้อง**
   ```
   แก้ไข: ตรวจสอบ WHT Tax Types มี Account กำหนดไว้
   ```

4. **Code ไม่ได้ Update**
   ```
   แก้ไข: Restart Odoo Server และ Update Module
   ```

### ปัญหา: Payment ไม่หัก WHT

**สาเหตุที่เป็นไปได้:**

1. **Writeoff Account ไม่ใช่ WHT Account**
   ```
   แก้ไข: ตรวจสอบ Account Type และ WHT Account flag
   ```

2. **Payment Difference Handling = "Mark as fully paid"**
   ```
   แก้ไข: ต้องเป็น "Keep open" เพื่อสร้าง Writeoff Entry
   ```

## การทดสอบด้วย Script

รันใน Odoo Shell:
```bash
cd /opt/instance1/odoo17
./odoo-bin shell -d your_database --no-http
```

ใน Shell:
```python
exec(open('/opt/instance1/odoo17/custom-addons/l10n_th_account_tax/tools/test_wht_auto_fill.py').read())
```

## ผลลัพธ์ที่คาดหวัง

### Auto Fill สำเร็จ:
- ✅ Payment Amount ลดลงตาม WHT
- ✅ WHT Fields มีค่าถูกต้อง
- ✅ Writeoff Account เป็น WHT Account
- ✅ สร้าง Payment พร้อม WHT Journal Entry

### Auto Fill ไม่สำเร็จ:
- ❌ Payment Amount ยังเป็นจำนวนเต็ม
- ❌ WHT Fields ว่าง
- ❌ ไม่มี Writeoff การตั้งค่า

## Debug Steps

1. **ตรวจสอบ Log**
   ```bash
   tail -f /var/log/odoo/odoo.log | grep -i wht
   ```

2. **ตรวจสอบใน Browser Console**
   - F12 → Console
   - ดู Error messages

3. **ตรวจสอบ Database**
   ```sql
   SELECT * FROM account_withholding_tax;
   SELECT * FROM account_account WHERE wht_account = true;
   ```

## หมายเหตุ

- ต้อง Update Module หลังแก้ไข Code
- ต้อง Clear Browser Cache
- ตรวจสอบ User Permissions สำหรับ WHT
