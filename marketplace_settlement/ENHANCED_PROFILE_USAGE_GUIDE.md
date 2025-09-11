# Marketplace Settlement - Enhanced Profile Usage Guide

## การใช้งาน Profile Customer Settlement ที่ปรับปรุงแล้ว

### การเข้าถึง Profile Settings
1. ไปที่เมนู **Accounting** → **Marketplace Settlement** → **Profiles**
2. เลือก Profile ที่ต้องการแก้ไข หรือสร้าง Profile ใหม่

### ฟีเจอร์ใหม่ที่ปรับปรุง

#### 1. เลือก Account Code ได้ทุกหมวด
- **commission_account_id** (บัญชีค่าคอมมิชชั่น)
- **service_fee_account_id** (บัญชีค่าบริการ)  
- **advertising_account_id** (บัญชีค่าโฆษณา)
- **logistics_account_id** (บัญชีค่าขนส่ง)
- **other_expense_account_id** (บัญชีค่าใช้จ่ายอื่นๆ)
- **settlement_account_id** (บัญชีสำหรับ Settlement)

**ก่อนการปรับปรุง:** จำกัดเฉพาะ Expense accounts เท่านั้น  
**หลังการปรับปรุง:** เลือกได้จาก **ทุกประเภทบัญชี** (Asset, Liability, Equity, Income, Expense)

#### 2. เลือก Journal Entry ได้ทุกหมวด
- **journal_id** (Journal สำหรับ Settlement)

**ก่อนการปรับปรุง:** จำกัดเฉพาะ Sales journals เท่านั้น  
**หลังการปรับปรุง:** เลือกได้จาก **ทุกประเภท Journal** (Sales, Purchase, Cash, Bank, Miscellaneous)

### ส่วนที่ถูกลบออก

#### 1. Default Vendor Settings (ไม่ได้ใช้งาน)
- ~~vendor_partner_id~~ - Default Vendor Partner
- ~~purchase_journal_id~~ - Purchase Journal
- ~~default_vat_rate~~ - Default VAT Rate (%)
- ~~default_wht_rate~~ - Default WHT Rate (%)
- ~~vat_tax_id~~ - VAT Purchase Tax
- ~~wht_tax_id~~ - WHT Tax

#### 2. Thai WHT Configuration (ไม่ได้ใช้งาน)
- ~~use_thai_wht~~ - Use Thai WHT
- ~~thai_income_tax_form~~ - Default Income Tax Form
- ~~thai_wht_income_type~~ - Default WHT Income Type

### หน้าจอใหม่ที่เรียบง่าย

#### Settlement Configuration
```
Customer Settlement:
├── Marketplace Partner     (เลือกลูกค้า Marketplace เช่น Shopee, Lazada)
├── Default Journal        (เลือกได้ทุกประเภท Journal)
└── Settlement Account     (เลือกได้ทุกประเภทบัญชี)

Default Expense Accounts:
├── Commission Account     (เลือกได้ทุกประเภทบัญชี)
├── Service Fee Account    (เลือกได้ทุกประเภทบัญชี)
├── Advertising Account    (เลือกได้ทุกประเภทบัญชี)
├── Logistics Account      (เลือกได้ทุกประเภทบัญชี)
└── Other Expenses Account (เลือกได้ทุกประเภทบัญชี)
```

#### Notes
- ช่องสำหรับบันทึกหมายเหตุเพิ่มเติม

### ตัวอย่างการใช้งาน

#### สร้าง Profile สำหรับ Shopee
1. **Profile Name:** "Shopee Thailand Profile"
2. **Trade Channel:** "Shopee"
3. **Marketplace Partner:** เลือกลูกค้า Shopee
4. **Default Journal:** เลือก Journal ที่ต้องการ (ไม่จำกัดเฉพาะ Sales)
5. **Settlement Account:** เลือกบัญชีลูกหนี้ หรือบัญชีอื่นตามต้องการ
6. **Commission Account:** เลือกบัญชีค่าคอมมิชชั่น (สามารถเป็น Asset, Expense หรืออื่นๆ)

#### ใช้ Profile ในการสร้าง Settlement
1. กดปุ่ม **"Create Settlement"** ใน Profile
2. ระบบจะใช้ค่า default จาก Profile ที่ตั้งไว้
3. ผู้ใช้สามารถปรับเปลี่ยนได้ตามต้องการ

### ข้อดีของการปรับปรุง

#### เพิ่มความยืดหยุ่น
- เลือก Account ได้หลากหลายตามความเหมาะสม
- เลือก Journal ได้ตามการใช้งานจริง
- ไม่ถูกจำกัดโดยระบบ

#### ลดความซับซ้อน
- หน้าจอเรียบง่าย เน้นที่ฟังก์ชันที่ใช้งานจริง
- ลบส่วนที่ไม่จำเป็นออกไป
- ง่ายต่อการตั้งค่าและใช้งาน

#### ปรับปรุงประสิทธิภาพ
- โหลดหน้าจอเร็วขึ้น
- ลดข้อผิดพลาดจากการตั้งค่าที่ซับซ้อน
- เน้นที่ Customer Settlement ที่เป็นฟังก์ชันหลัก

### การอัปเกรด

เมื่ออัปเกรดโมดูล ข้อมูลเดิมจะ:
- **ข้อมูลสำคัญ:** ยังคงอยู่ (Profile name, trade channel, marketplace partner, accounts)
- **ข้อมูลที่ลบ:** จะถูกลบอย่างปลอดภัย (vendor settings, Thai WHT settings)
- **การใช้งาน:** ไม่มีผลกระทบต่อ settlements ที่มีอยู่แล้ว

### การสนับสนุน

หากมีปัญหาในการใช้งาน:
1. ตรวจสอบ Profile settings ให้ครบถ้วน
2. ตรวจสอบสิทธิ์การเข้าถึงบัญชีและ journals
3. ตรวจสอบ migration logs หากมีข้อผิดพลาดจากการอัปเกรด
