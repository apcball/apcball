# Marketplace Settlement Profile Enhancement

## Overview
ปรับปรุง Profile Customer Settlement ตามความต้องการ:
- เลือก account code ได้ทุกหมวด (ไม่จำกัดเฉพาะ expense accounts)
- เลือก Journal Entry ได้ทุกหมวด (ไม่จำกัดเฉพาะ sale journals)
- ลบ Default Vendor Setting และ Thai WHT Configuration ออกจาก Profile

## Changes Made

### 1. Model Changes (models/profile.py)

#### Removed Fields:
- `vendor_partner_id` - Default Vendor Partner
- `purchase_journal_id` - Purchase Journal  
- `default_vat_rate` - Default VAT Rate (%)
- `default_wht_rate` - Default WHT Rate (%)
- `vat_tax_id` - VAT Purchase Tax
- `wht_tax_id` - WHT Tax
- `use_thai_wht` - Use Thai WHT
- `thai_income_tax_form` - Default Income Tax Form
- `thai_wht_income_type` - Default WHT Income Type

#### Enhanced Fields:
- Removed domain restrictions from all account fields:
  - `commission_account_id`
  - `service_fee_account_id`
  - `advertising_account_id`
  - `logistics_account_id`
  - `other_expense_account_id`

- Removed domain restrictions from journal fields:
  - `journal_id` - Now allows all journal types (not just sale)
  - `settlement_account_id` - Now allows all account types

#### Updated Methods:
- `get_default_line_config()` - Removed VAT/WHT rate returns
- `_onchange_trade_channel()` - Removed VAT/WHT rate setting, kept pattern setting only

### 2. View Changes (views/profile_views.xml)

#### Form View Simplified:
- Removed "Vendor Bill Configuration" page completely
- Removed "Thai Localization" page completely
- Removed domain restrictions from account and journal fields
- Updated tree view to remove vendor and tax rate columns
- Kept only essential configuration in "Settlement Configuration" page

#### Remaining Sections:
1. **Settlement Configuration**
   - Customer Settlement (Partner, Journal, Settlement Account)
   - Default Expense Accounts (All account types selectable)

2. **Notes**
   - Free text field for additional configuration notes

### 3. Migration Script

Created migration script (`migrations/17.0.1.1.0/post-migration.py`):
- Drops obsolete database columns safely
- Handles existing data gracefully
- Logs migration progress

### 4. Version Update

Updated module version from `17.0.1.0.0` to `17.0.1.1.0` to reflect enhancements.

## Benefits

### Enhanced Flexibility:
1. **Account Selection**: ผู้ใช้สามารถเลือก account code จากทุกหมวดหมู่ ไม่จำกัดเฉพาะ expense accounts
2. **Journal Selection**: ผู้ใช้สามารถเลือก Journal Entry จากทุกประเภท ไม่จำกัดเฉพาะ sale journals
3. **Simplified Interface**: หน้าจอง่ายขึ้น เน้นที่ฟังก์ชันหลักที่ใช้งานจริง

### Cleaner Configuration:
- ลบส่วนที่ไม่ได้ใช้งาน (Vendor Settings, Thai WHT) ออกไป
- ลดความซับซ้อนในการตั้งค่า Profile
- เน้นที่ Customer Settlement ที่เป็นฟังก์ชันหลัก

## Installation Instructions

1. อัปเดตโมดูลใน Odoo:
   ```bash
   # ใน Odoo shell หรือ command line
   ./odoo-bin -d your_database -u marketplace_settlement
   ```

2. Migration script จะทำงานอัตโนมัติเพื่อลบ fields ที่ไม่ใช้แล้ว

3. ตรวจสอบ Profile ที่มีอยู่ - ควรจะยังคงข้อมูลสำคัญไว้ได้

## Testing

สามารถทดสอบการเปลี่ยนแปลงได้โดย:
1. เปิด Marketplace Profiles
2. สร้าง Profile ใหม่หรือแก้ไข Profile ที่มีอยู่
3. ตรวจสอบว่าสามารถเลือก account และ journal จากทุกหมวดได้
4. ตรวจสอบว่าหน้าจอง่ายขึ้นและไม่มี vendor/WHT settings

## Backward Compatibility

Migration script ได้รับการออกแบบให้ปลอดภัย:
- ข้อมูลที่สำคัญจะยังคงอยู่
- Fields ที่ลบออกจะถูกลบอย่างปลอดภัย
- ไม่มีผลกระทบต่อ settlements ที่มีอยู่แล้ว
