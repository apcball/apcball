# คำสั่งตรวจสอบ Configuration

กรุณารัน SQL queries ต่อไปนี้เพื่อตรวจสอบ configuration:

## 1. ตรวจสอบ Tax Configuration

```sql
SELECT 
    t.id,
    t.name,
    t.is_vat_undue,
    t.undue_conversion_tax_id,
    t.undue_input_vat_account_id,
    target_tax.name as target_tax_name,
    input_account.code as input_account_code,
    input_account.name as input_account_name
FROM account_tax t
LEFT JOIN account_tax target_tax ON t.undue_conversion_tax_id = target_tax.id
LEFT JOIN account_account input_account ON t.undue_input_vat_account_id = input_account.id
WHERE t.is_vat_undue = true
AND t.active = true;
```

## 2. ตรวจสอบบัญชี 116400 และ 116600

```sql
SELECT 
    id,
    code,
    name,
    deprecated,
    company_id
FROM account_account
WHERE code IN ('116400', '116600')
ORDER BY code;
```

## 3. ตรวจสอบ Tax Undue Lines

```sql
SELECT 
    tul.id,
    tul.name,
    tul.tax_amount,
    tul.used_tax_amount,
    tul.state,
    undue_acc.code as undue_account_code,
    undue_acc.name as undue_account_name,
    t.name as tax_name,
    t.undue_input_vat_account_id,
    input_acc.code as input_account_code
FROM tax_undue_line tul
LEFT JOIN account_account undue_acc ON tul.account_id = undue_acc.id
LEFT JOIN account_tax t ON tul.tax_id = t.id
LEFT JOIN account_account input_acc ON t.undue_input_vat_account_id = input_acc.id
ORDER BY tul.id DESC
LIMIT 5;
```

## 4. ตรวจสอบ Journal Entries ที่มีปัญหา

```sql
SELECT 
    am.id,
    am.name,
    am.ref,
    aml.id as line_id,
    aa.code as account_code,
    aa.name as account_name,
    aml.debit,
    aml.credit
FROM account_move am
JOIN account_move_line aml ON am.id = aml.move_id
JOIN account_account aa ON aml.account_id = aa.id
WHERE am.ref LIKE '%Clear Undue VAT%'
OR am.ref LIKE '%VAT Usage%'
ORDER BY am.id DESC
LIMIT 20;
```

## คาดหวังผลลัพธ์:

### Query 1 (Tax Config):
- is_vat_undue: true
- target_tax_name: ควรเป็น "7%" หรือภาษีซื้อปกติ
- **input_account_code: ควรเป็น "116400"** ← สำคัญมาก!
- input_account_name: ภาษีซื้อ

### Query 2 (Accounts):
- 116400: ภาษีซื้อ (deprecated: false)
- 116600: ภาษีซื้อไม่ถึงกำหนด (deprecated: false)

### Query 4 (Journal Entries):
- ควรเห็น 2 lines:
  - Line 1: 116400 (Dr > 0, Cr = 0)
  - Line 2: 116600 (Dr = 0, Cr > 0)
- ถ้าเห็น 111002: แสดงว่ามีปัญหา!
