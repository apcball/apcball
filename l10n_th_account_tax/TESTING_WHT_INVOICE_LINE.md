# Testing Guide for WHT Invoice Line Implementation

## การทดสอบระบบ WHT ใหม่

### 1. ทดสอบการเพิ่ม WHT ใน Invoice Line

#### ขั้นตอนการทดสอบ:

1. **สร้าง Invoice ใหม่**
   ```
   Accounting > Customers > Invoices > Create
   หรือ
   Accounting > Vendors > Bills > Create
   ```

2. **เพิ่ม Invoice Line**
   - เลือก Product
   - ใส่ Quantity และ Unit Price
   - **ใหม่**: เลือก WHT tax ในคอลัมน์ "WHT"

3. **ตรวจสอบการคำนวณ**
   - ยอด WHT Amount ควรคำนวณอัตโนมัติ
   - ยอดรวม WHT ควรแสดงในส่วน Totals

4. **Post Invoice**
   - คลิก "Post" 
   - ตรวจสอบว่า Withholding Tax Moves ถูกสร้าง
   - ไปที่ Tab "Withholding Moves" เพื่อดูข้อมูล

### 2. ทดสอบสร้างใบหัก ณ ที่จ่าย

#### ขั้นตอนการทดสอบ:

1. **จาก Invoice ที่มี WHT**
   - คลิกปุ่ม "Create WHT Cert"
   - หรือ คลิก "⇒ Create withholding tax cert."

2. **ตรวจสอบใบหัก ณ ที่จ่าย**
   - ควรมีข้อมูล Base Amount และ WHT Amount
   - ควรมี Income Type และ Description

3. **ตรวจสอบการเชื่อมโยง**
   - ใบหัก ณ ที่จ่ายควรเชื่อมโยงกับ Invoice
   - แสดงสถานะใน Invoice

### 3. ทดสอบ Scenarios ต่างๆ

#### Scenario 1: Single WHT Type
```
Product: Services
Amount: 10,000 THB
WHT: 3% Services
Expected WHT: 300 THB
```

#### Scenario 2: Multiple Lines with Same WHT
```
Line 1: Services 10,000 THB, 3% WHT
Line 2: Services 5,000 THB, 3% WHT
Expected Total WHT: 450 THB
```

#### Scenario 3: Multiple WHT Types
```
Line 1: Services 10,000 THB, 3% WHT
Line 2: Rental 5,000 THB, 5% WHT
Expected: 2 separate WHT certificates
```

### 4. การตรวจสอบข้อมูล

#### Database Records ที่ควรสร้าง:

1. **account.move.line** ควรมี:
   - `wht_invoice_line_tax` = WHT tax ที่เลือก
   - `wht_invoice_amount` = ยอด WHT ที่คำนวณ
   - `wht_invoice_base` = ยอดฐาน WHT

2. **account.withholding.move** ควรสร้าง:
   - `move_id` = Invoice ID
   - `partner_id` = Customer/Vendor
   - `amount_income` = Base amount
   - `amount_wht` = WHT amount
   - `wht_tax_id` = WHT tax

3. **withholding.tax.cert** ควรสร้าง:
   - `move_id` = Invoice ID
   - `partner_id` = Customer/Vendor
   - `wht_line` = WHT lines with amounts

### 5. ทดสอบ Edge Cases

#### Case 1: ลบ WHT จาก Line
- เลือก WHT tax แล้วลบออก
- ยอด WHT ควรเป็น 0
- Withholding Move ไม่ควรสร้าง

#### Case 2: แก้ไข Amount
- เปลี่ยน Unit Price
- ยอด WHT ควรคำนวณใหม่อัตโนมัติ

#### Case 3: Cancel Invoice
- Cancel Invoice ที่มี WHT
- Withholding Moves ควรถูก cancel ด้วย

### 6. Performance Testing

#### ทดสอบกับข้อมูลจำนวนมาก:
- Invoice ที่มี 50+ lines
- แต่ละ line มี WHT
- ตรวจสอบเวลาในการ compute และ post

### 7. Error Handling Testing

#### ทดสอบ Error Cases:
1. **ไม่มี WHT Account**
   - สร้าง WHT tax ที่ไม่มี account
   - ระบบควรแสดง error

2. **ข้อมูล Partner ไม่ครบ**
   - Invoice ไม่มี partner
   - ควรแสดง error ที่เหมาะสม

3. **Duplicate WHT Certificate**
   - พยายามสร้างใบหัก ณ ที่จ่าย 2 ครั้ง
   - ควรแสดง warning

### 8. Integration Testing

#### ทดสอบกับ Modules อื่น:
1. **กับ Accounting**
   - Journal Entries ถูกต้อง
   - Chart of Accounts

2. **กับ Payments**
   - Payment กับ Invoice ที่มี WHT
   - WHT certificate จาก payment

3. **กับ Reports**
   - Tax Report แสดง WHT
   - Withholding Tax Report

### 9. UI/UX Testing

#### ทดสอบการใช้งาน:
1. **Field Visibility**
   - WHT field แสดงเฉพาะใน Invoice
   - ซ่อนใน Journal Entry ปกติ

2. **Performance UI**
   - การคำนวณไม่ทำให้ UI ช้า
   - Field compute รวดเร็ว

3. **User Experience**
   - ง่ายต่อการเลือก WHT
   - แสดงข้อมูลชัดเจน

### 10. Regression Testing

#### ตรวจสอบไม่กระทบของเดิม:
1. **ระบบ Tax Invoice เดิม**
   - ยังทำงานปกติ
   - ไม่มี WHT ผิดใน Tax Invoice

2. **ระบบ WHT เดิม** 
   - `wht_tax_id` ยังใช้งานได้
   - Journal Entry WHT ปกติ

3. **การ Upgrade**
   - ข้อมูลเดิมไม่เสียหาย
   - Migration script ทำงาน

## Expected Results

✅ **Pass Criteria:**
- WHT field แสดงใน invoice line
- คำนวณยอด WHT ถูกต้อง
- สร้าง Withholding Move อัตโนมัติ
- สร้างใบหัก ณ ที่จ่ายได้
- ไม่กระทบระบบเดิม

❌ **Fail Criteria:**
- WHT ถูกบันทึกใน Tax Invoice
- ไม่สร้าง Withholding Move
- Error ในการคำนวณ
- UI แสดงผิด
- กระทบระบบเดิม

## Test Environment

- **Odoo Version**: 17.0
- **Module**: l10n_th_account_tax
- **Test Data**: Thai company with WHT setup
- **User Roles**: Account Manager, Account User

## Test Schedule

1. **Unit Testing**: แต่ละ function ทำงานถูกต้อง
2. **Integration Testing**: ทำงานร่วมกับ modules อื่น
3. **User Acceptance Testing**: ผู้ใช้ทดสอบจริง
4. **Performance Testing**: ทดสอบกับข้อมูลจำนวนมาก
5. **Regression Testing**: ไม่กระทบของเดิม
