# Profile-Settlement Integration - การใช้งานจริง

## การปรับปรุงที่เสร็จสิ้น ✅

### 1. Profile ใช้งานร่วมกับ Create Settlement ได้จริง
- **Profile Form:** มีปุ่ม "Create Settlement" ที่ดึงค่าจาก Profile
- **Auto-populate:** ระบบดึงค่า marketplace partner, journal, settlement account อัตโนมัติ
- **Profile Reference:** Settlement บันทึก profile_id เพื่อใช้อ้างอิงต่อไป

### 2. ดึงค่าจาก Profile ไปใช้งานได้จริง
- **Wizard Integration:** `_onchange_profile()` ดึงค่าทั้งหมดจาก Profile
- **Context Data:** Profile ส่งข้อมูล context ให้ wizard ครบถ้วน
- **Account Settings:** Profile accounts ถูกใช้ในการสร้าง vendor bills

### 3. ลงบัญชีได้จริงตาม setup ใน Profile
- **Settlement Account:** ใช้ `settlement_account_id` จาก Profile ในการลงบัญชี
- **Journal Selection:** ใช้ journal จาก Profile (ไม่จำกัดเฉพาะ sale journals)
- **Account Flexibility:** Account codes เลือกได้ทุกหมวด (Asset, Liability, Equity, Income, Expense)

## การใช้งานทีละขั้นตอน

### ขั้นตอนที่ 1: ตั้งค่า Profile
```
1. ไปที่ Accounting → Marketplace Settlement → Profiles
2. สร้าง Profile ใหม่ หรือแก้ไข Profile ที่มีอยู่:
   
   Settlement Configuration:
   ├── Marketplace Partner: เลือกลูกค้า (เช่น Shopee Co., Ltd.)
   ├── Default Journal: เลือก Journal ที่ต้องการ (ทุกประเภท)
   └── Settlement Account: เลือกบัญชีสำหรับ Settlement (ทุกประเภท)
   
   Default Expense Accounts:
   ├── Commission Account: บัญชีค่าคอมมิชชั่น (ทุกประเภท)
   ├── Service Fee Account: บัญชีค่าบริการ (ทุกประเภท)
   ├── Advertising Account: บัญชีค่าโฆษณา (ทุกประเภท)
   ├── Logistics Account: บัญชีค่าขนส่ง (ทุกประเภท)
   └── Other Expenses Account: บัญชีค่าใช้จ่ายอื่น (ทุกประเภท)
```

### ขั้นตอนที่ 2: สร้าง Settlement จาก Profile
```
1. ใน Profile Form กดปุ่ม "Create Settlement"
2. ระบบจะเปิด Settlement Wizard พร้อมข้อมูลจาก Profile:
   ✓ Trade Channel: อัตโนมัติ
   ✓ Marketplace Partner: อัตโนมัติ
   ✓ Journal: อัตโนมัติ
   ✓ Settlement Account: อัตโนมัติ
   
3. เลือก invoices ที่ต้องการ settle
4. กด "Create" เพื่อสร้าง Settlement
```

### ขั้นตอนที่ 3: สร้าง Vendor Bills
```
จาก Profile:
1. กดปุ่ม "Create Vendor Bill" ใน Profile
2. ระบบสร้าง Vendor Bill พร้อม invoice lines ที่ใช้ accounts จาก Profile

จาก Settlement:
1. กดปุ่ม "Create Vendor Bill" ใน Settlement (ถ้ามี Profile)
2. ระบบสร้าง Vendor Bill ที่ link กับ Settlement และใช้ accounts จาก Profile
```

### ขั้นตอนที่ 4: ลงบัญชี Settlement
```
1. Settlement ใช้ accounts ตาม setup ใน Profile:
   - Settlement Account: จาก Profile หรือ Marketplace Partner
   - Journal: จาก Profile
   - Customer Accounts: จาก invoices
   
2. Journal Entry จะเป็น:
   Dr. Settlement Account (จาก Profile)     XXX
       Cr. Customer A/R                         XXX
       Cr. Customer B/R                         XXX
```

## ตัวอย่างการใช้งานจริง

### Profile Setup สำหรับ Shopee
```
Profile Name: Shopee Thailand Profile
Trade Channel: Shopee
Marketplace Partner: Shopee Co., Ltd.
Default Journal: Sales Journal (หรือ Journal อื่นๆ ตามต้องการ)
Settlement Account: 1120001 - A/R Shopee (หรือบัญชีอื่นๆ ตามต้องการ)

Expense Accounts:
├── Commission Account: 6110001 - Commission Expense  
├── Service Fee Account: 6120001 - Service Fee Expense
├── Advertising Account: 6130001 - Advertising Expense
├── Logistics Account: 6140001 - Logistics Expense
└── Other Expenses Account: 6190001 - Other Expenses
```

### การสร้าง Settlement
```
1. จาก Profile กดปุ่ม "Create Settlement"
2. ระบบจะ auto-populate:
   - Trade Channel: Shopee
   - Marketplace Partner: Shopee Co., Ltd.
   - Journal: Sales Journal  
   - Settlement Account: 1120001 - A/R Shopee
   
3. เลือก invoices ที่ต้องการ settle
4. สร้าง Settlement และระบบจะลงบัญชี:
   Dr. 1120001 - A/R Shopee               100,000
       Cr. 1110001 - A/R Customer A             30,000
       Cr. 1110002 - A/R Customer B             40,000  
       Cr. 1110003 - A/R Customer C             30,000
```

### การสร้าง Vendor Bills จาก Profile
```
1. จาก Profile กดปุ่ม "Create Vendor Bill"
2. ระบบสร้าง Vendor Bill พร้อม invoice lines:
   - Commission Fee → 6110001 - Commission Expense
   - Service Fee → 6120001 - Service Fee Expense
   - Advertising Fee → 6130001 - Advertising Expense
   - Logistics Fee → 6140001 - Logistics Expense
   
3. ผู้ใช้กรอกจำนวนเงินและ post vendor bill
4. Link vendor bill กับ settlement เพื่อทำ AR/AP netting
```

## ข้อดีของการปรับปรุง

### 1. ความยืดหยุ่นในการเลือก Accounts
- **ก่อน:** จำกัดเฉพาะ expense accounts
- **หลัง:** เลือกได้ทุกประเภทบัญชี (Asset, Liability, Equity, Income, Expense)

### 2. ความยืดหยุ่นในการเลือก Journals  
- **ก่อน:** จำกัดเฉพาะ sales journals
- **หลัง:** เลือกได้ทุกประเภท journals (Sales, Purchase, Cash, Bank, Miscellaneous)

### 3. การใช้งานที่เรียบง่าย
- **Profile-driven:** ตั้งค่าครั้งเดียวใน Profile ใช้ได้หลายครั้ง
- **Auto-populate:** ระบบดึงค่าอัตโนมัติ ลดข้อผิดพลาด
- **Linked Creation:** สร้าง vendor bills ที่ link กับ settlement ได้ทันที

### 4. การลงบัญชีที่ถูกต้อง
- **Account Mapping:** ใช้ accounts ตาม setup ใน Profile
- **Consistency:** การลงบัญชีสม่ำเสมอตาม Profile
- **Traceability:** สามารถติดตาม Profile ที่ใช้ได้

## การทดสอบ

ทุกฟีเจอร์ผ่านการทดสอบแล้ว:
✓ Syntax validation
✓ Profile methods integration  
✓ Settlement-Profile integration
✓ Wizard-Profile integration
✓ View enhancements
✓ Account flexibility
✓ Journal flexibility

## สรุป

Profile Customer Settlement ตอนนี้:
- **ใช้งานร่วมกับ Create Settlement ได้จริง** ✅
- **ดึงค่าจาก Profile ไปใช้งานได้จริง** ✅
- **ลงบัญชีได้จริงตาม setup ใน Profile** ✅
- **เลือก Account Code ได้ทุกหมวด** ✅
- **เลือก Journal Entry ได้ทุกหมวด** ✅
- **สร้าง Vendor Bills ด้วย Profile accounts** ✅
