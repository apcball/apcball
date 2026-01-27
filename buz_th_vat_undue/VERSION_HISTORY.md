# buz_th_vat_undue - Version History

## Version 17.0.1.0.5 (2026-01-18)
### ✨ New Features
- **Wizard สำหรับเลือกวันที่ลงบัญชี**: เมื่อกด "Use VAT" จะเปิด wizard ให้เลือกวันที่ลงบัญชีได้
  - User สามารถเลือกวันที่ที่ต้องการ (default: วันนี้)
  - แสดงสรุปจำนวนรายการและยอดรวม
  - แสดงรายละเอียด Tax Undue Lines ที่จะประมวลผล

### 🔧 Technical Changes
- เพิ่ม `vat.undue.use.wizard` model
- แยก `action_use_vat()` และ `_process_use_vat()` ใน tax.undue.line
- รับ accounting_date จาก context แทนใช้ tax_invoice_date

### 📁 New Files
- `wizard/vat_undue_use_wizard.py`
- `wizard/vat_undue_use_wizard_views.xml`
- `WIZARD_USE_VAT.md`

---

## Version 17.0.1.0.4 (2026-01-18)
### 🐛 Bug Fix: Tax Invoice Control
- **ปัญหา:** Tax Invoice ถูกสร้างทันทีเมื่อ post bill → ปรากฏใน Tax Report ทันที
- **แก้ไข:** ป้องกันการสร้าง tax invoice ตอน post bill, สร้างตอนกด "Use VAT" แทน

### 🔧 Technical Changes
- Override `account_move_line.create()` เพื่อลบ tax invoice สำหรับ VAT Undue
- ปรับปรุง `action_use_vat()` ให้สร้าง tax invoice พร้อม tax_base_amount และ balance
- Integration กับ `l10n_th_account_tax` module

### 📁 New Files
- `models/account_move_line.py`
- `TAX_INVOICE_CONTROL.md`

---

## Version 17.0.1.0.3
### 🔧 Improvements
- แก้ไข logic การสร้าง Journal Entry
- เพิ่ม validation ครบถ้วน
- เพิ่ม diagnostic wizard

### 📁 Files
- `wizard/vat_undue_diagnostic_wizard.py`
- `FIX_SUMMARY.md`
- `DEBUG_CHECK_CONFIG.md`

---

## Version 17.0.1.0.0 - Initial Release
### 🎯 Core Features
- จัดการ VAT Undue (ภาษีซื้อยังไม่ถึงกำหนด)
- บันทึกภาษีไปยัง VAT Undue Account (116600)
- จัดการผ่านหน้า Taxes Undue
- แปลง VAT Undue → Input VAT
- Integration กับ Thai Tax Reports

### 📦 Core Models
- `account.tax` - เพิ่มฟิลด์ VAT Undue configuration
- `account.move` - จัดการสร้าง Tax Undue Lines
- `tax.undue.line` - Model หลักสำหรับจัดการ VAT Undue

---

## Dependencies
- `account` - Odoo Accounting Core
- `l10n_th` - Thailand Localization
- `l10n_th_account_tax` - Thailand Tax Invoice Management

## License
LGPL-3

## Author
APCBALL

## Support
For issues or questions, please contact your system administrator.
