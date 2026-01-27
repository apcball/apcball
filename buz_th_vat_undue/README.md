# Thailand VAT Undue Management

## Objective
Create an Odoo 17 custom module to support Thailand VAT Undue (ภาษีซื้อยังไม่ถึงกำหนด) workflow.

## Features
- Selecting VAT Undue 7% on Vendor Bills
- Deferring VAT posting to a VAT Undue account
- Managing VAT Undue in a dedicated Tax Undue screen
- Batch converting VAT Undue → Input VAT
- **Tax Invoice บันทึกใน Tax Report เฉพาะตอนกด "Use VAT" เท่านั้น**
- Integrating with Thailand VAT reports (Tax Invoice / PP30)

## Configuration
1. Go to Accounting > Configuration > Taxes.
2. Select or create a Purchase Tax.
3. Check "Is VAT Undue".
4. Set "Target VAT Tax" (e.g., Input VAT 7%).
5. Set "Input VAT Account" (e.g., 116400).
6. Ensure the Tax Grid is set to None or a specific Undue grid so it doesn't appear on the main VAT report immediately (logic handled by code).

## Usage Flow

### 1. Create Vendor Bill with VAT Undue
1. Create a Vendor Bill.
2. Select the **VAT Undue 7%** tax on invoice lines.
3. Fill in "**Tax Invoice Number**" and "**Tax Invoice Date**" (required).
4. Post the bill.

**Result:**
- Tax amount goes to **VAT Undue Account (116600)**.
- Creates a record in **Taxes Undue** screen.
- **Tax Invoice is NOT created yet** (will not appear in Tax Reports).

### 2. Use VAT (When Payment is Made)
1. Go to **Accounting > Taxes Undue**.
2. Select lines to clear (paid invoices).
3. Click "**Use VAT**".
4. **Select Accounting Date** in the wizard (default: today).
5. Click "**Confirm Use VAT**".

**Result:**
- Creates journal entry with the selected accounting date:
  ```
  Dr 116400 (Input VAT)    70.00
     Cr 116600 (VAT Undue)        70.00
  ```
- **Creates Tax Invoice record** for Tax Reports (PP30).
- Tax now appears in Input VAT reports.

## Important Notes

### Tax Invoice Behavior
- **ตอน Post Bill:** ไม่สร้าง Tax Invoice → ไม่ปรากฏใน Tax Report
- **ตอนกด Use VAT:** สร้าง Tax Invoice → ปรากฏใน Tax Report
- Tax Invoice จะใช้เลขที่และวันที่จาก Vendor Bill ต้นฉบับ

### Credit Note Behavior (v1.0.6)
**Case 1: CN ก่อน Use VAT**
- สร้าง Tax Undue Line แบบลบ
- อัพเดท original line: refunded_tax_amount

**Case 2: CN หลัง Use VAT** ⭐
- **Reverse journal entry** จาก Use VAT อัตโนมัติ
- ลบ Tax Invoice Records
- Reset Tax Undue Line state → undue
- ไม่สร้าง Reclassification Entry ซ้ำซ้อน

### Accounting Entries
```
เมื่อ Post Bill (VAT Undue):
Dr Expenses             1,000.00
Dr 116600 (VAT Undue)      70.00
   Cr Payable                      1,070.00

เมื่อกด "Use VAT":
Dr 116400 (Input VAT)      70.00
   Cr 116600 (VAT Undue)           70.00

เมื่อ Credit Note (หลัง Use VAT):
1. CN Entry:
   Dr Payable              1,070.00
      Cr Expenses                  1,000.00
      Cr VAT Undue                     70.00

2. Reversal Entry (Auto):
   Dr VAT Undue               70.00
      Cr Input VAT                     70.00
```

