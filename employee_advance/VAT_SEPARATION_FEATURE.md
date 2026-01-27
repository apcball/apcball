# VAT-Based Bill Separation Feature - Implementation Guide

## 📋 Overview

ฟีเจอร์นี้เพิ่มความสามารถในการแยก Vendor Bills ตามสถานะ VAT (ภาษี) นอกเหนือจากการแยกตามคู่ค้า (Vendor) และวันที่

**เป้าหมาย**: ให้ Expense Line ที่มี VAT/Tax ถูกสร้างเป็น Bill แยกจาก Expense Line ที่ไม่มี VAT/Tax

---

## 🎯 Business Logic

### Grouping Key Structure
```
BEFORE: (partner_id, company_id, currency_id, expense_date)
AFTER:  (partner_id, company_id, currency_id, expense_date, has_vat)
```

### VAT Detection
```python
has_vat = bool(expense.tax_ids)
# True  : expense มี tax_ids → ต้องแยก bill
# False : expense ไม่มี tax_ids → แยก bill
```

### Auto Mode Trigger
```
is_auto_mode = True เมื่อ:
  1. Multiple vendors > 1 OR
  2. Mixed VAT configuration (some with tax, some without)
```

---

## 🔄 Bill Creation Workflow

### Before Implementation
```
Expense Lines:
  ├─ Item A: 5,000 บาท (Vendor: V1) ❌ No Tax
  ├─ Item B: 3,000 บาท (Vendor: V1) ✅ With Tax (7%)
  └─ Item C: 2,000 บาท (Vendor: V1) ❌ No Tax

Grouping: (V1, 1, THB, 2024-01-15)

Result: 1 Bill รวมทุกอย่าง
  Bill V1 - 10,000 บาท (mixed: some with tax, some without)
```

### After Implementation
```
Expense Lines:
  ├─ Item A: 5,000 บาท (Vendor: V1) ❌ No Tax
  ├─ Item B: 3,000 บาท (Vendor: V1) ✅ With Tax (7%)
  └─ Item C: 2,000 บาท (Vendor: V1) ❌ No Tax

Grouping: (V1, 1, THB, 2024-01-15, has_vat)

Result: 2 Bills แยกตามสถานะ VAT
  Bill V1 - No VAT (With VAT) - 8,000 บาท
    └─ Item A: 5,000 (no tax)
    └─ Item C: 2,000 (no tax)
  
  Bill V1 - Date: 2024-01-15 (With VAT) - 3,000 บาท
    └─ Item B: 3,000 (with 7% VAT)
```

---

## 📝 Implementation Changes

### 1. Modified: `_compute_auto_mode()`

**Location**: `models/expense_sheet.py` - Line ~85

**Changes**:
```python
@api.depends("expense_line_ids")
def _compute_auto_mode(self):
    for sheet in self:
        # Check vendors
        unique_vendors = set(exp.expense_vendor_id.id if exp.expense_vendor_id else None 
                           for exp in sheet.expense_line_ids)
        
        # NEW: Check for mixed VAT configurations
        has_tax = any(exp.tax_ids for exp in sheet.expense_line_ids)
        has_no_tax = any(not exp.tax_ids for exp in sheet.expense_line_ids)
        mixed_vat = has_tax and has_no_tax
        
        # AUTO mode triggered by MULTIPLE VENDORS or MIXED VAT
        sheet.is_auto_mode = len(unique_vendors) > 1 or mixed_vat
```

**Impact**: 
- ✅ AUTO mode now triggers when mixing VAT and non-VAT expenses
- ✅ Even single vendor can trigger AUTO mode if mixed VAT

### 2. Enhanced: `_compute_vendor_summary()`

**Location**: `models/expense_sheet.py` - Line ~110

**Changes**:
```python
@api.depends("expense_line_ids", "is_auto_mode")  
def _compute_vendor_summary(self):
    for sheet in self:
        if sheet.is_auto_mode:
            # ... vendor detection ...
            
            # NEW: VAT detection
            has_vat = any(exp.tax_ids for exp in sheet.expense_line_ids)
            has_no_vat = any(not exp.tax_ids for exp in sheet.expense_line_ids)
            
            # Build summary with VAT info
            vat_summary = []
            if has_vat:
                vat_summary.append("📊 With VAT")
            if has_no_vat:
                vat_summary.append("📄 Without VAT")
            
            if vat_summary:
                summary_parts.append(f"Bill Types: {' | '.join(vat_summary)}")
```

**Display Example**:
```
🤖 AUTO MODE - แยกบิลตาม: Vendors: Supplier A | Bill Types: 📊 With VAT | 📄 Without VAT
```

### 3. Core: `_create_bills_by_vendor_grouping()`

**Location**: `models/expense_sheet.py` - Line ~355

**Changes**:
```python
def _create_bills_by_vendor_grouping(self):
    """Group by vendor, date, AND VAT status"""
    groups = {}
    
    for expense in self.expense_line_ids:
        # ... partner logic ...
        
        # NEW: Detect VAT status
        has_vat = bool(expense.tax_ids)
        
        # NEW: Include has_vat in group key
        group_key = (
            partner_id,
            company_id,
            currency_id,
            expense_date,
            has_vat  # ← NEW: Separate by VAT
        )
        
        # Initialize group with has_vat tracking
        if group_key not in groups:
            groups[group_key] = {
                'partner_id': partner_id,
                'company_id': company_id,
                'currency_id': currency_id,
                'expense_line_date': expense_date,
                'has_vat': has_vat,  # ← NEW
                'expenses': self.env['hr.expense'],
                'is_vendor': bool(expense.expense_vendor_id)
            }
```

**Impact**:
- ✅ Bills now separated by `(vendor, date, vat_status)`
- ✅ Same vendor + same date but different VAT → different bills
- ✅ Proper accounting segregation

### 4. Updated: `_create_single_bill_for_vendor_group_date()`

**Location**: `models/expense_sheet.py` - Line ~456

**Changes**:
```python
def _create_single_bill_for_vendor_group_date(self, group_data):
    """Create bill with VAT status label"""
    # ... existing logic ...
    
    # NEW: Get VAT status from group_data
    has_vat = group_data.get('has_vat', False)
    
    # Create bill reference
    bill_ref = f'Expense Sheet {self.name}'
    if is_vendor:
        bill_ref += f' - {partner_name} - Date: {expense_line_date}'
    else:
        bill_ref += f' - Employee: {partner_name} - Date: {expense_line_date}'
    
    # NEW: Append VAT status to reference
    vat_label = '(With VAT)' if has_vat else '(No VAT)'
    bill_ref += f' {vat_label}'
    
    # Bill reference example:
    # "Expense Sheet ES001 - Supplier A - Date: 2024-01-15 (With VAT)"
    # "Expense Sheet ES001 - Supplier A - Date: 2024-01-15 (No VAT)"
```

**Impact**:
- ✅ Clear identification in bill reference
- ✅ Easy tracking of which expenses have VAT
- ✅ Better for auditing

---

## 📊 Use Case Examples

### Case 1: Mixed VAT from Single Vendor

**Scenario**:
```
Vendor: ABC Supplies
Date: 2024-01-15

Expenses:
  1. Pens: 500 บาท (no tax)
  2. Ink: 1,500 บาท (7% VAT)
  3. Paper: 1,000 บาท (no tax)
```

**Result**:
```
Bill 1: ABC Supplies - Date: 2024-01-15 (No VAT)
  └─ Pens: 500
  └─ Paper: 1,000
  └─ Total: 1,500 บาท

Bill 2: ABC Supplies - Date: 2024-01-15 (With VAT)
  └─ Ink: 1,500
  └─ Total: 1,607.50 บาท (1,500 + 107.50 VAT)
```

### Case 2: Multiple Vendors with Mixed VAT

**Scenario**:
```
Vendor A, Vendor B, no vendor

Vendor A:
  - Item 1: 2,000 (no tax)
  - Item 2: 1,500 (7% VAT)

Vendor B:
  - Item 3: 3,000 (7% VAT)
  - Item 4: 1,000 (no tax)

Employee:
  - Item 5: 500 (no tax)
```

**Result**:
```
4 Bills Created:

Bill 1: Vendor A - 2024-01-15 (No VAT)
  └─ Item 1: 2,000

Bill 2: Vendor A - 2024-01-15 (With VAT)
  └─ Item 2: 1,500 (+105 VAT)

Bill 3: Vendor B - 2024-01-15 (With VAT)
  └─ Item 3: 3,000 (+210 VAT)

Bill 4: Vendor B - 2024-01-15 (No VAT)
  └─ Item 4: 1,000

Bill 5: Employee - 2024-01-15 (No VAT)
  └─ Item 5: 500
```

### Case 3: Same Vendor, Different Dates, Mixed VAT

**Scenario**:
```
Vendor: ABC Supplies

2024-01-15:
  - Item A: 1,000 (no tax)
  - Item B: 500 (7% VAT)

2024-01-16:
  - Item C: 2,000 (no tax)
  - Item D: 1,500 (7% VAT)
```

**Result**:
```
4 Bills Created:

Bill 1: ABC Supplies - Date: 2024-01-15 (No VAT)
  └─ Item A: 1,000

Bill 2: ABC Supplies - Date: 2024-01-15 (With VAT)
  └─ Item B: 500 (+35 VAT)

Bill 3: ABC Supplies - Date: 2024-01-16 (No VAT)
  └─ Item C: 2,000

Bill 4: ABC Supplies - Date: 2024-01-16 (With VAT)
  └─ Item D: 1,500 (+105 VAT)
```

---

## 🔍 Bill Separation Logic Summary

### Grouping Dimensions

| Dimension | Type | Purpose |
|-----------|------|---------|
| Vendor/Employee | Partner ID | Who to invoice |
| Company | Company ID | Legal entity |
| Currency | Currency ID | Transaction currency |
| Date | Date | Accounting period |
| **VAT Status** | ✅ **NEW** | Tax treatment |

### Bill Created When
```
Key = (partner_id, company_id, currency_id, expense_date, has_vat)
      ↓
      ONE UNIQUE KEY = ONE BILL
```

### Examples
```
Key A: (V1, Comp1, THB, 2024-01-15, FALSE)  → Bill A (no VAT)
Key B: (V1, Comp1, THB, 2024-01-15, TRUE)   → Bill B (with VAT)

Same partner, company, currency, date
BUT different VAT status = DIFFERENT BILLS
```

---

## 📧 UI/UX Changes

### Before
```
Expense Sheet ES001
  is_auto_mode: True
  vendor_summary: "🤖 AUTO MODE - แยกบิลตาม: Vendors: ABC Supplies"
```

### After
```
Expense Sheet ES001
  is_auto_mode: True
  vendor_summary: "🤖 AUTO MODE - แยกบิลตาม: Vendors: ABC Supplies | Bill Types: 📊 With VAT | 📄 Without VAT"
```

### Bill References

Before:
```
Bill 1: "Expense Sheet ES001 - ABC Supplies - Date: 2024-01-15"
```

After:
```
Bill 1: "Expense Sheet ES001 - ABC Supplies - Date: 2024-01-15 (No VAT)"
Bill 2: "Expense Sheet ES001 - ABC Supplies - Date: 2024-01-15 (With VAT)"
```

---

## 💡 Benefits

### ✅ Accounting Accuracy
- VAT expenses separated from non-VAT expenses
- Proper VAT accounting per bill
- Clear audit trail

### ✅ Tax Compliance
- Simplified VAT reporting
- Easy segregation for tax documents
- Proper cost allocation

### ✅ Vendor Management
- Each vendor bill clearly shows VAT status
- Easier invoice matching with vendor statements
- Better cost tracking

### ✅ USER Experience
- Automatic bill separation (no manual work)
- Clear labeling in bill references
- Visual indicators in AUTO MODE summary

---

## 🚀 How to Use

### Step 1: Create Expense Sheet with Mixed VAT

```
Employee: John Doe
Expense Lines:
  ├─ Office Supplies: 1,000 THB (Vendor: ABC) (No Tax)
  ├─ Professional Service: 5,000 THB (Vendor: ABC) (7% VAT)
  └─ Misc: 500 THB (No Vendor) (No Tax)
```

### Step 2: System Detects AUTO MODE

```
is_auto_mode: ✓ TRUE
Reason: Mixed VAT configuration detected
vendor_summary: "🤖 AUTO MODE - แยกบิลตาม: Vendors: ABC | Bill Types: 📊 With VAT | 📄 Without VAT"
```

### Step 3: Approve Expense Sheet

```
Manager clicks "Approve"
↓
System automatically creates:
  - Bill 1: ABC - No VAT (1,000 บาท)
  - Bill 2: ABC - With VAT (5,000 + 350 = 5,350 บาท)
  - Bill 3: Employee - No VAT (500 บาท)
```

### Step 4: Accounting Reviews Bills

```
Bill 1: Reference = "Expense Sheet ES001 - ABC - 2024-01-15 (No VAT)"
Bill 2: Reference = "Expense Sheet ES001 - ABC - 2024-01-15 (With VAT)"
Bill 3: Reference = "Expense Sheet ES001 - Employee: John Doe - 2024-01-15 (No VAT)"

Each bill has correct tax treatment
```

---

## ⚙️ Technical Details

### Modified Functions

1. `HrExpenseSheet._compute_auto_mode()`
   - Added VAT detection logic
   - Triggers AUTO mode on mixed VAT

2. `HrExpenseSheet._compute_vendor_summary()`
   - Added VAT summary display
   - Shows bill type indicators (📊 📄)

3. `HrExpenseSheet._create_bills_by_vendor_grouping()`
   - Added `has_vat` to group key
   - Creates separate groups per VAT status

4. `HrExpenseSheet._create_single_bill_for_vendor_group_date()`
   - Appends VAT label to bill reference
   - Tracks VAT status in bill data

### Database Impact
- ✅ No new tables required
- ✅ No schema changes
- ✅ Backward compatible
- ✅ Existing bills unaffected

### Performance
- ✅ Minimal overhead (simple boolean check)
- ✅ No additional queries
- ✅ Grouping logic optimized

---

## 🧪 Testing Checklist

- [ ] Single vendor with mixed VAT → 2 bills created
- [ ] Multiple vendors with mixed VAT → Multiple bills correct
- [ ] Single vendor, same date, mixed VAT → 2 bills separated
- [ ] Multiple dates, mixed VAT → Bills grouped by date + VAT
- [ ] No VAT expenses → 1 bill (AUTO mode may not trigger)
- [ ] All VAT expenses → 1 bill (AUTO mode may not trigger)
- [ ] Bill references show correct VAT labels
- [ ] AUTO MODE indicator shows VAT summary
- [ ] WHT clearing works with split bills
- [ ] Advance box linking works with all bills

---

## 📞 Support & Documentation

### Related Files
- `models/expense_sheet.py` - Core implementation
- `models/hr_expense.py` - Expense line fields
- `MODULE_ANALYSIS.md` - Overall module architecture

### Future Enhancements
- [ ] Tax type filtering (VAT vs WHT vs other)
- [ ] Smart vendor naming in bills with VAT indicator
- [ ] VAT summary report across all bills
- [ ] Configurable VAT separation behavior

---

## 📝 Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2024-01-12 | Initial VAT separation implementation |

---

## 📌 Key Takeaway

**Before**: Same vendor + same date = 1 bill (mixed VAT)
**After**: Same vendor + same date + same VAT status = 1 bill (clean separation)

This ensures proper accounting segregation and simplified tax reporting.
