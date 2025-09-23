
# HR Expense Advance Clearing (Odoo 17)

## 📌 Concept
This module enhances the **Expense Management** workflow in Odoo 17 by introducing a proper **Advance / Petty Cash Clearing** mechanism.  
Default Odoo behavior forces employee expenses into **Accounts Payable (AP)**. With this module, companies can manage **Advance Accounts (141101)** directly, supporting Thai accounting practices.

## 🎯 Goals
- Allow employees to request and clear advances seamlessly.
- Post journal entries directly against **Advance Account (141101)** instead of AP.
- Support **VAT** (Input Tax) and **WHT** (Withholding Tax) entries automatically.
- Provide **Audit Trail**: Link Expense → Journal Entry → Advance Box.
- Track **per-employee advance balance** in real-time.

## ⚙️ Accounting Flow

### 1. Advance Top-up
When the company gives advance to an employee:
```
Dr 141101 Employee Advance
    Cr 102101 Bank
```

### 2. Expense Submission (Clear from Advance)
When the employee submits expenses with VAT/WHT:
```
Dr 65xxx Expense
Dr 119xxx VAT Input
    Cr 141101 Employee Advance
    Cr 213xxx Withholding Tax Payable (if applicable)
```

### 3. Settlement
- If **expense < advance** → employee returns the balance:
```
Dr 102101 Bank
    Cr 141101 Employee Advance
```
- If **expense > advance** → company pays the difference:
```
Dr 141101 Employee Advance
    Cr 102101 Bank
```

## 🏗️ Components
- **Advance Box per Employee**
  - Tracks advance balance
  - Defines advance account (141101)

- **Wizard: Advance Top-up / Return**
  - Handles JE creation for top-up or refund

- **Expense Integration**
  - Checkbox *Clear from Advance*
  - Redirects credit from Payable → Advance Account
  - Posts VAT/WHT automatically

## ✅ Benefits
- Matches real Thai accounting practices
- Eliminates misuse of AP for advances
- Simplifies reconciliation & audit
- Provides clear visibility of advance balances per employee

---

🔧 Author: MOGEN IT (Prototype for further development)
