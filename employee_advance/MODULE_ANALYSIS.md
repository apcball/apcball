# วิเคราะห์โมดูล Employee Advance (Odoo 17)

## 📋 สรุปโมดูล

โมดูล **Employee Advance** เป็นระบบบริหารจัดการเงินทดรองจ่ายสำหรับพนักงาน ในบริษัท โดยรองรับ:
- การจัดการกล่องเบิกจ่ายกลาง (Advance Box) ต่อพนักงาน
- การติดตามยอดเงินคงเหลือ
- การสร้างบิลอัตโนมัติจากค่าใช้จ่าย
- การตัดหนี้ (Reconciliation) ด้วย WHT (ภาษีหัก ณ ที่จ่าย)
- การเติมเงินเบิกจ่ายอัตโนมัติ (Refill-to-Base)

---

## 🏗️ สถาปัตยกรรมโมดูล

### โมดูลหลัก (Core Models)

#### 1. **EmployeeAdvanceBox** (`advance_box.py`)
รุ่นแบบกล่องเบิกจ่ายที่จัดเก็บเงินสำหรับแต่ละพนักงาน

**ฟิลด์หลัก:**
```
name              : ชื่อกล่อง (คำนวณอัตโนมัติจาก employee name)
employee_id       : พนักงาน (M2O)
account_id        : บัญชี 113001 (เงินทดรองจ่าย)
journal_id        : Journal สำหรับการเติมเงิน
remember_base_amount : ยอดเบิกฐาน (สำหรับ Refill-to-Base)
balance          : ยอดคงเหลือ (คำนวณ)
refill_ids       : ประวัติการเติมเงิน (O2M)
refill_count     : จำนวนครั้งการเติม (คำนวณ)
currency_id      : สกุลเงิน
company_id       : บริษัท
```

**ฟังก์ชันสำคัญ:**
- `_compute_balance()` : คำนวณยอดคงเหลือจาก Journal Entries
  - ค้นหา account.move.line ตามบัญชี (113001) + partner filtering
  - คำนวณ: Debit - Credit = Balance
  - ฟิลเตอร์ด้วย partner เพื่อแยกพนักงานแต่ละคน
  
- `_compute_name()` : สร้างชื่อจาก "{Employee Name} - Advance Box"

- `_get_employee_partner()` : หาพาร์ทเนอร์ของพนักงาน (address_home_id หรือ user.partner_id)

---

#### 2. **AdvanceBoxRefill** (`advance_box_refill.py`)
ประวัติการเติมเงินลงในกล่องเบิกจ่าย

**ฟิลด์หลัก:**
```
name              : ชื่อการเติม (วันที่ + จำนวนเงิน)
box_id            : กล่องเบิกจ่าย (M2O)
amount            : จำนวนเงินที่เติม
date              : วันที่เติม
journal_id        : Journal ที่ใช้
move_id           : Journal Entry ที่สร้าง
state             : สถานะ (draft, posted, cancelled)
currency_id       : สกุลเงิน
company_id        : บริษัท
```

**ฟังก์ชันสำคัญ:**
- `_create_refill_journal_entry()` : สร้าง Journal Entry เมื่อเติมเงิน
- `action_post()` : โพสต์ Refill แล้วอัปเดตยอดคงเหลือ
- `action_cancel()` : ยกเลิกการเติมเงิน (Draft และ Posted states)

---

#### 3. **HrExpenseSheet** (ขยาย) - (`expense_sheet.py`)
ขยายฟีเจอร์ของเอกสารค่าใช้จ่ายเพื่อรองรับการเบิกจ่าย

**ฟิลด์เพิ่มเติม:**
```
clear_mode              : โหมดการตัดหนี้ (reimburse_employee, pay_vendor, mixed)
bill_ids                : บิลที่สร้าง (M2M)
is_billed               : ว่ามีการสร้างบิลแล้วหรือไม่
use_advance             : ใช้เบิกจ่ายหรือไม่
advance_box_id          : กล่องเบิกจ่าย (M2O) - auto-filled จาก employee
is_auto_mode            : โหมดอัตโนมัติ (True เมื่อ vendors > 1)
vendor_summary          : สรุปผู้จำหน่าย (แสดงข้อมูล AUTO MODE)
can_clear_advance_wht   : สามารถ Clear ด้วย WHT หรือไม่
payment_ids             : การชำระเงิน (M2M คำนวณ)
```

**ฟังก์ชันสำคัญ:**

- **`action_approve_expense_sheets()`** : อนุมัติและสร้างบิล
  - เรียก `action_create_vendor_bills()`
  - ให้สถานะของชีท = "done"

- **`action_create_vendor_bills()`** : สร้างบิลอัตโนมัติ
  - เลือกระหว่าง:
    - `_create_bills_by_vendor_grouping()` : AUTO mode (แยกตามคู่ค้า)
    - `_create_single_bill_for_vendor_group()` : Manual mode (บิลเดียว)

- **`_create_bills_by_vendor_grouping()`** : แยกบิลตามกลุ่ม
  - จัดกลุ่มตาม: (vendor, expense_line_date)
  - สร้างบิลแยกสำหรับแต่ละกลุ่ม
  - ลิงก์ advance_box_id ไปยังทุกบิล

- **`action_clear_advance()`** : ตัดหนี้เบิกจ่าย
  - สร้าง Journal Entry ด้วยอัตโนมัติ
  - ไม่ต้องเปิด Register Payment wizard
  - Debit: Expense Account, Credit: Advance Box Account

- **`action_open_wht_clear_advance_wizard()`** : เปิด WHT Clear Wizard
  - ตรวจสอบ: use_advance, advance_box_id, state
  - ผ่านข้อมูลไปยัง Wizard

---

#### 4. **AccountMove** (ขยาย) - (`account_move.py`, `wht_integration.py`)
ขยายฟีเจอร์ของบิลเพื่อรองรับการตัดหนี้เบิกจ่าย

**ฟิลด์เพิ่มเติม:**
```
advance_box_id          : กล่องเบิกจ่าย (M2O)
is_expense_advance_bill : เป็นบิลเบิกจ่ายหรือไม่
expense_sheet_id        : เอกสารค่าใช้จ่ายที่เกี่ยวข้อง (M2O)
has_wht_cert            : มี WHT Certificate หรือไม่ (คำนวณ)
```

**ฟังก์ชันสำคัญ:**

- **`action_clear_advance_from_bill()`** : ตัดหนี้ปกติ
  - หา expense sheet ที่เกี่ยวข้อง (จากลิงก์หรือ invoice_origin)
  - สร้าง Journal Entry เพื่อตัดหนี้
  - Debit: Advance Box Account, Credit: Bill Account

- **`action_open_wht_clear_advance_wizard_from_bill()`** : เปิด WHT Wizard
  - ตรวจสอบ: move_type='in_invoice', state='posted', amount_residual > 0
  - ส่งข้อมูลไปยัง Wizard

- **`_clear_advance_using_advance_box()`** : สร้าง Journal Entry
  - สร้าง 2 lines:
    - Debit: 113001 (Advance Box Account)
    - Credit: Bill Account (สำหรับตัดหนี้)

---

### Wizard Models

#### 1. **WhtClearAdvanceWizard** (`wht_clear_advance_wizard.py`)
Wizard สำหรับตัดหนี้ด้วย WHT

**ฟิลด์หลัก:**
```
expense_sheet_id         : เอกสารค่าใช้จ่าย (M2O)
employee_id              : พนักงาน (M2O)
advance_box_id           : กล่องเบิกจ่าย (M2O)
wht_amount               : จำนวน WHT (คำนวณ)
clear_amount             : จำนวนที่ตัดหนี้ (คำนวณ)
wht_tax_lines            : บรรทัด WHT (O2M)
bill_id                  : บิล (M2O)
```

**ฟังก์ชันสำคัญ:**
- `default_get()` : ตั้งค่าเริ่มต้นจากบิล/ชีทอัตโนมัติ
- `_validate_data_integrity()` : ตรวจสอบความถูกต้อง
- `action_clear_advance_wht()` : บันทึกข้อมูล
- `_create_wht_journal_entries()` : สร้าง Journal Entries สำหรับ WHT

---

#### 2. **AdvanceRefillBaseWizard** (`advance_refill_base_wizard.py`)
Wizard สำหรับเติมเงินเบิกจ่ายไปยังฐานที่กำหนด

**ฟิลด์หลัก:**
```
advance_box_id      : กล่องเบิกจ่าย (M2O)
target_amount       : ยอดเบิกฐาน (คำนวณจาก remember_base_amount)
current_balance     : ยอดปัจจุบัน (คำนวณ)
refill_amount       : จำนวนที่ต้องเติม (คำนวณ)
journal_id          : Journal (คำนวณ)
memo                : หมายเหตุ
```

---

#### 3. **SettlementWizard** (`settlement_wizard.py`)
Wizard สำหรับปิดบัญชีเบิกจ่าย (Settlement)

**ฟังก์ชันหลัก:**
- `action_settle()` : ปิดบัญชีและสร้าง Final Journal Entry

---

### Data Models

#### SecurityGroups & Permissions (`security/`)
```
- employee_advance.group_advance_manager    : ผู้บริหารเบิกจ่าย
- employee_advance.group_advance_approver   : ผู้อนุมัติเบิกจ่าย
- employee_advance.group_advance_user       : ผู้ใช้ทั่วไป
```

---

## 📊 Workflow (กระบวนการทำงาน)

### 1️⃣ **การจัดเตรียมอนุมัติ (Setup)**
```
HR Manager
  ↓
สร้าง Employee Advance Box
  ↓ (ต่อ Employee)
set remember_base_amount (ยอดเบิกฐาน)
set account_id = 113001 (Advance Box Account)
set journal_id = Bank/Cash Journal
```

### 2️⃣ **การเบิกจ่ายเบื้องต้น (Initial Disbursement)**
```
Accounting
  ↓
สร้าง Journal Entry:
  Debit: 113001 (Advance Box) 
  Credit: Bank (เบิกจากธนาคาร)
  Amount: Initial Amount
```

### 3️⃣ **การรายงานค่าใช้จ่าย (Expense Reporting)**
```
Employee
  ↓
สร้าง Expense Sheet
  ├─ expense_line_ids: ค่าใช้จ่ายแต่ละรายการ
  ├─ use_advance: ✓ (ตัดจากกล่องเบิก)
  └─ advance_box_id: อัตโนมัติจาก employee
```

### 4️⃣ **การอนุมัติ (Approval)**
```
Manager
  ↓
ดู Expense Sheet
  ↓
คลิก "Approve"
  ↓
ระบบสร้าง Vendor Bills อัตโนมัติ
```

### 5️⃣ **การสร้างบิล (Bill Creation)**
```
Expense Sheet
  ↓
ตรวจสอบ is_auto_mode:
  ├─ True (vendors > 1):
  │    สร้างบิลแยกตามคู่ค้า
  │    ├─ Vendor Bill 1: product A
  │    ├─ Vendor Bill 2: product B
  │    └─ Employee Bill: other items
  │
  └─ False (vendors ≤ 1):
       สร้างบิลเดียว
```

### 6️⃣ **การตัดหนี้เบิกจ่าย (Clear Advance)**
```
Accounting
  ↓
เปิด Vendor Bill
  ↓
บิล → Action "Clear with Advance" หรือ "Clear with WHT"
  ↓
Option 1: Normal Clear
  ├─ สร้าง Journal Entry:
  │   Debit: 113001 (Advance Box)
  │   Credit: Bill Receivable
  │   Amount: Bill Amount
  │
Option 2: WHT Clear (มี Tax ประเภท WHT)
  ├─ Wizard เข้า: ใส่ WHT Amount
  ├─ สร้าง Journal Entries:
  │   1. Debit: 113001, Credit: Bill (จำนวน Bill - WHT)
  │   2. Debit: 2405 (WHT Payable), Credit: Bill (WHT Amount)
  │   3. (Optional) WHT Certificate
```

### 7️⃣ **เติมเงินเบิกจ่าย (Refill to Base)**
```
Accounting
  ↓
เปิด Advance Box
  ↓
คลิก "Refill to Base"
  ↓
Wizard:
  Current: 50,000 บาท
  Target: 100,000 บาท
  Refill Amount: 50,000 บาท
  ↓
สร้าง Refill History + Journal Entry:
  Debit: 113001 (Advance Box)
  Credit: Bank
  Amount: 50,000 บาท
```

---

## 🔑 Key Features

### ✅ **1. Auto Advance Box Assignment**
- Expense Sheet อัตโนมัติ assign advance_box_id
- หา advance_box จาก employee.advance_box_id (default)
- หรือค้นหา advance_box ที่พบว่าเป็นของ employee

### ✅ **2. Vendor-Based Auto Grouping (AUTO MODE)**
```
is_auto_mode = True (เมื่อ vendors > 1)

Expense Lines:
  1. item A → Vendor 1 → Bill 1
  2. item B → Vendor 2 → Bill 2
  3. item C (no vendor) → Employee → Bill 3

clear_mode:
  - 'pay_vendor' (if all have vendors)
  - 'reimburse_employee' (if no vendors)
  - 'mixed' (if both exist)
```

### ✅ **3. Expense Line Separation**
- แต่ละ expense line เป็นบรรทัดแยกในบิล (ไม่ group by product)
- ติดตาม original expense line เพื่อการรายงาน

### ✅ **4. Date Grouping**
- จัดกลุ่มตาม expense_line_date ด้วย
- ตัวอย่าง: Item A (2024-01-15) vs Item A (2024-01-16) → บิลต่างกัน

### ✅ **5. WHT Integration**
- ตรวจสอบว่าบิลมี WHT lines หรือไม่
- คำนวณ WHT base amount (ก่อน VAT)
- สร้าง WHT Certificate references
- Clear advance ด้วย WHT Amount

### ✅ **6. Cross-Employee Advance Clearing**
- สามารถ clear advance box ของพนักงานคนอื่นได้
- เช่น Manager clear เงินทดรองของ Staff

### ✅ **7. Refill History**
- ติดตามประวัติการเติมเงิน
- สามารถยกเลิก (Cancel) Refill ได้ (Draft/Posted)
- linked journal entries

---

## 🗂️ File Structure

```
employee_advance/
├── __manifest__.py          # Module manifest
├── __init__.py              # Package init
├── models/
│   ├── __init__.py
│   ├── advance_box.py       # ✨ กล่องเบิกจ่าย
│   ├── advance_box_refill.py # ✨ ประวัติการเติม
│   ├── hr_employee.py       # ✨ ขยาย Employee
│   ├── expense_sheet.py     # 🔥 ขยาย Expense Sheet (core logic)
│   ├── hr_expense.py        # ✨ ขยาย Expense Line
│   ├── account_move.py      # 🔥 ขยาย Account Move (bill logic)
│   ├── account_move_line.py # ✨ ขยาย Move Line
│   ├── account_payment_register.py # ✨ Payment Register
│   ├── res_config_settings.py # ✨ ตั้งค่าระบบ
│   ├── utils_journal.py     # 🔧 Journal utilities
│   └── wht_integration.py   # 🔥 WHT integration
│
├── wizards/
│   ├── __init__.py
│   ├── wht_clear_advance_wizard.py # 🔑 Clear with WHT
│   ├── advance_refill_base_wizard.py # 🔑 Refill to Base
│   ├── settlement_wizard.py # 🔑 Settlement
│   ├── expense_sheet_bill_preview_wizard.py
│   ├── link_advance_wizard.py
│   └── mark_as_done_confirmation_wizard.py
│
├── views/
│   ├── margin_approval_views.xml
│   ├── sale_order_views.xml
│   ├── pending_approval_views.xml
│   ├── templates.xml
│   ├── report_margin_approval.xml
│   ├── margin_approval_dashboard.xml
│   ├── advance_box_views.xml # ✨ Views สำหรับ advance box
│   ├── expense_sheet_views.xml # ✨ Views สำหรับ expense sheet
│   ├── hr_expense_views.xml # ✨ Views สำหรับ expense line
│   ├── hr_employee_views.xml # ✨ Views สำหรับ employee
│   ├── res_config_settings_views.xml
│   ├── wht_clear_advance_wizard_views.xml
│   ├── advance_refill_base_wizard_views.xml
│   ├── advance_settlement_wizard_views.xml
│   ├── advance_box_refill_views.xml
│   ├── wizard_refill_advance_box_views.xml
│   └── advance_box_refill_menus.xml
│
├── security/
│   ├── margin_approval_security.xml
│   └── ir.model.access.csv
│
├── data/
│   ├── mail_activity_types.xml
│   ├── batch_actions.xml
│   ├── wht_taxes.xml
│   └── cleanup_wizards.xml
│
└── documentation/
    ├── README.md
    ├── REFILL_FEATURE_IMPLEMENTATION.md
    ├── SETTLEMENT_TECHNICAL_DOCS.md
    ├── WHT_CLEAR_ADVANCE_README.md
    └── ... [more docs]
```

---

## 🔧 Configuration & Setup

### 1. **ตั้งค่าบัญชี (Chart of Accounts)**
```
113001 - เงินทดรองจ่าย (Advance Box Account)
214001 - เจ้าหนี้ (Bill Payable)
2405xx - ภาษีหัก ณ ที่จ่าย (WHT Payable)
```

### 2. **ตั้งค่า Employee**
```
HR Manager
  ↓ สร้าง Advance Box
  ├─ Employee: Staff A
  ├─ Account: 113001
  ├─ Base Amount: 100,000 บาท
  ├─ Journal: Bank
  └─ ลิงก์ไปยัง HR Employee
```

### 3. **ตั้งค่า Expense Line**
```
ใน Expense Line สามารถระบุ:
  ├─ expense_vendor_id: ผู้จำหน่าย (optional)
  ├─ wht_tax_id: ภาษีหัก (optional)
  └─ amount: จำนวนเงิน
```

### 4. **ตั้งค่าระบบ (Res Config Settings)**
```
Settings > Employees Advance
  ├─ Notify User: ผู้รับแจ้งเตือน
  ├─ Notify Group: กลุ่มรับแจ้งเตือน
  ├─ Activity Type: ประเภท Activity
  └─ Clear Advance Journal: Journal สำหรับ Clear
```

---

## ⚡ Performance & Optimization

### Balance Computation Optimization
```python
# ❌ ช้า: read_group + heavy field access
balance = sum(lines.mapped('amount_currency'))

# ✅ เร็ว: domain filtering + simple math
lines = env['account.move.line'].search(domain)
balance = sum(lines.mapped('debit')) - sum(lines.mapped('credit'))
```

### Hang Prevention
- `default_get()` ไม่ trigger heavy computations
- `_refresh_balance_simple()` ใช้ cache invalidation แทน recalculation
- โหลดข้อมูลแยก parts เพื่อหลีกเลี่ยง timeout

---

## 🐛 Known Issues & Fixes

### 1. **WHT Reconcile Issue**
- **ปัญหา**: WHT Clear ทำให้ reconciliation ของบิลอื่นชำรุด
- **แก้ไข**: ให้ WHT ตัดหนี้เฉพาะบิลที่ระบุ (specific bill)

### 2. **Balance Computation Hang**
- **ปัญหา**: `_compute_balance()` timeout เมื่อมี move.line เยอะ
- **แก้ไข**: ใช้ cache invalidation + domain filtering เพื่อเร็วขึ้น

### 3. **Expense Line Separation**
- **ปัญหา**: expense line ถูก group by product แล้วหายรายการเดิม
- **แก้ไข**: สร้างบรรทัดแยกต่อ expense line (ไม่ group)

### 4. **Cross-Company Support**
- **ปัญหา**: Balance filter ไม่ filter by company
- **แก้ไข**: เพิ่ม company_id ลงใน domain filter

---

## 📈 Data Flow

```
┌─────────────────────────────────────┐
│ Employee Advance Flow               │
└─────────────────────────────────────┘

┌──────────────┐
│ Setup Phase  │
└──────┬───────┘
       ↓
   Create Advance Box
   (113001, Base Amount = 100K)
       ↓
   Create Initial JE
   (DR 113001, CR Bank)
       ↓
   Balance = 100,000 บาท
       
┌──────────────────┐
│ Expense Reporting│
└──────┬───────────┘
       ↓
   Employee creates Expense Sheet
   ├─ Line 1: Product A, 5K (Vendor: V1)
   ├─ Line 2: Product B, 3K (Vendor: V2)
   └─ Line 3: Misc, 2K (No vendor)
       ↓
   use_advance = ✓
   advance_box_id = auto-filled
       ↓
   Balance = 100,000 บาท (unchanged)
       
┌──────────────────┐
│ Approval Phase   │
└──────┬───────────┘
       ↓
   Manager approves
       ↓
   Create 3 Bills:
   ├─ Vendor Bill V1: 5K (Line 1)
   ├─ Vendor Bill V2: 3K (Line 2)
   └─ Employee Bill: 2K (Line 3)
   
   ALL Bills linked to advance_box_id
       ↓
   Bills status = Draft
       
┌──────────────────┐
│ Accounting Phase │
└──────┬───────────┘
       ↓
   Validate & Post Bills
       ↓
   Bill Status = Posted
       ↓
   For each Bill:
   ├─ Option 1: Clear with Advance
   │  └─ Create JE:
   │     DR 113001 (Advance Box)
   │     CR 21401x (Bill Payable)
   │     Amount: Bill Amount
   │
   └─ Option 2: Clear with WHT
      └─ Open Wizard
         ├─ Calc WHT Amount
         ├─ Create JEs:
         │  1. DR 113001, CR 21401x (Bill - WHT)
         │  2. DR 2405xx, CR 21401x (WHT)
         └─ Create WHT Cert

┌──────────────────┐
│ Balance Update   │
└──────┬───────────┘
       ↓
   After Clear with Advance:
   ├─ DR 113001: 10,000 บาท
   └─ Balance = 100,000 - 10,000 = 90,000 บาท
```

---

## 🎯 Use Cases

### Case 1: Normal Employee Advance
```
1. Setup: 
   - Advance Box: 100,000 บาท
   
2. Expense: 
   - Office Supplies: 5,000 บาท
   
3. Bill: 
   - Auto-created for 5,000 บาท
   
4. Clear: 
   - Clear with Advance: DR 113001, CR Bill
   - Balance: 95,000 บาท
```

### Case 2: Multi-Vendor Expenses (AUTO MODE)
```
1. Expense Sheet:
   - Item 1: 10K, Vendor: Supplier A
   - Item 2: 8K, Vendor: Supplier B
   - Item 3: 2K, No vendor
   
2. is_auto_mode = TRUE
   clear_mode = 'mixed'
   
3. Bills Created:
   - Bill 1 (Supplier A): 10K
   - Bill 2 (Supplier B): 8K
   - Bill 3 (Employee): 2K
```

### Case 3: WHT Clearing
```
1. Bill: 100,000 บาท (with 10% WHT)
   
2. Open WHT Wizard:
   - Bill Amount: 100,000
   - WHT Amount: 10,000
   - Clear Amount: 90,000
   
3. JEs Created:
   - JE 1: DR 113001, CR Bill (90,000)
   - JE 2: DR 2405xx, CR Bill (10,000)
   
4. Advance Box: 100,000 - 100,000 = 0 บาท
```

---

## 🚀 Best Practices

### ✅ DO
- ✓ สร้าง Advance Box ต่อพนักงาน
- ✓ ตั้งค่า Base Amount ที่เหมาะสม
- ✓ ลิงก์ Expense Line ไปยัง Vendor เมื่อมี
- ✓ ใช้ Refill Wizard สำหรับการเติมเงิน
- ✓ ตรวจสอบ WHT Certificate สำหรับสรุปภาษี

### ❌ DON'T
- ✗ ไม่ควรเบิกเงินมากเกินไป (Balance checking)
- ✗ ไม่ควร Manual JE overwrite ค่า advance balance
- ✗ ไม่ควรลบ Expense Sheet ที่ approved แล้ว
- ✗ ไม่ควร Clear ด้วยวิธีอื่นนอกจากใช้ Wizard

---

## 📞 Support & Documentation

โมดูลมีไฟล์ documentation ดังนี้:
- `README.md` - สรุปและ flow
- `REFILL_FEATURE_IMPLEMENTATION.md` - feature refill
- `SETTLEMENT_TECHNICAL_DOCS.md` - Settlement feature
- `WHT_CLEAR_ADVANCE_README.md` - WHT clearing

---

## 📝 Summary

| ด้าน | รายละเอียด |
|------|----------|
| **Purpose** | บริหารจัดการเงินทดรองจ่ายพนักงาน |
| **Main Models** | EmployeeAdvanceBox, AdvanceBoxRefill, HrExpenseSheet (extended), AccountMove (extended) |
| **Core Features** | Auto Grouping, WHT Integration, Refill to Base, Settlement |
| **Key Workflow** | Setup → Expense → Approve → Bill → Clear Advance |
| **Security** | Role-based access (Manager, Approver, User) |
| **Integration** | HR, Accounting, Mail, WHT Certificate |
| **Status** | ✅ Stable & Production-ready |

