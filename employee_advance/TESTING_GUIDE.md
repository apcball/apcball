# VAT Separation Feature - Testing Guide

## 🧪 Pre-Testing Checklist

- [ ] Module installed successfully
- [ ] No Python syntax errors
- [ ] Database migrated
- [ ] Users with proper access rights
- [ ] Test vendors configured
- [ ] Test employees with advance boxes
- [ ] Tax configuration ready

---

## 🎯 Test Cases

### Test Case 1: Single Vendor with Mixed VAT

**Objective**: Verify bills are separated by VAT status for same vendor

**Setup**:
```
Employee: Staff A
Vendor: ABC Supplies

Expenses to create:
  1. Name: "Office Pens"
     Amount: 1,000 THB
     Vendor: ABC Supplies
     Tax: NONE
     
  2. Name: "Computer Mouse"
     Amount: 2,000 THB
     Vendor: ABC Supplies
     Tax: 7% VAT
     
  3. Name: "Paper Reams"
     Amount: 500 THB
     Vendor: ABC Supplies
     Tax: NONE
```

**Expected Results**:
```
✓ is_auto_mode = TRUE
  Reason: Mixed VAT detected (some with tax, some without)

✓ vendor_summary displays:
  "🤖 AUTO MODE - แยกบิลตาม: Vendors: ABC Supplies | Bill Types: 📊 With VAT | 📄 Without VAT"

✓ After Approval: 2 Bills Created

Bill 1:
  Reference: "Expense Sheet ES-001 - ABC Supplies - Date: 2024-01-XX (No VAT)"
  Total: 1,500 THB (1,000 + 500)
  Items: Office Pens, Paper Reams

Bill 2:
  Reference: "Expense Sheet ES-001 - ABC Supplies - Date: 2024-01-XX (With VAT)"
  Total: 2,140 THB (2,000 + 140 VAT)
  Items: Computer Mouse
```

**Test Steps**:
1. [ ] Create Expense Sheet with above expenses
2. [ ] Verify `is_auto_mode` is TRUE
3. [ ] Verify vendor_summary shows bill type indicators
4. [ ] Click "Approve"
5. [ ] Verify 2 bills created with correct references
6. [ ] Verify line items correctly distributed

---

### Test Case 2: Multiple Vendors with Mixed VAT

**Objective**: Verify separate bills per vendor and VAT combination

**Setup**:
```
Employee: Manager B

Expenses:
  1. Item: "Software License"
     Amount: 5,000 THB
     Vendor: Tech Corp
     Tax: 7% VAT
     
  2. Item: "Office Supplies"
     Amount: 1,500 THB
     Vendor: Tech Corp
     Tax: NONE
     
  3. Item: "Printing Services"
     Amount: 3,000 THB
     Vendor: Print Shop
     Tax: 7% VAT
     
  4. Item: "Delivery Charges"
     Amount: 500 THB
     Vendor: Print Shop
     Tax: NONE
```

**Expected Results**:
```
✓ is_auto_mode = TRUE
  Reason: Multiple vendors + mixed VAT

✓ vendor_summary:
  "🤖 AUTO MODE - แยกบิลตาม: Vendors: Tech Corp, Print Shop | Bill Types: 📊 With VAT | 📄 Without VAT"

✓ After Approval: 4 Bills Created

Bill 1: Tech Corp - (No VAT)
  Items: Office Supplies (1,500 THB)

Bill 2: Tech Corp - (With VAT)
  Items: Software License (5,000 + 350 VAT)

Bill 3: Print Shop - (With VAT)
  Items: Printing Services (3,000 + 210 VAT)

Bill 4: Print Shop - (No VAT)
  Items: Delivery Charges (500 THB)
```

**Test Steps**:
1. [ ] Create Expense Sheet with above expenses
2. [ ] Verify `is_auto_mode` = TRUE
3. [ ] Verify vendor_summary shows both vendors and VAT types
4. [ ] Click "Approve"
5. [ ] Verify 4 bills created
6. [ ] Verify each bill has correct VAT status in reference
7. [ ] Verify items correctly distributed

---

### Test Case 3: Same Vendor, Different Dates, Mixed VAT

**Objective**: Verify bills separated by date even with same vendor

**Setup**:
```
Employee: Staff C
Vendor: ABC Supplies (for all)

Expenses Date 1 (2024-01-15):
  1. Item A: 1,000 THB - NO TAX
  2. Item B: 500 THB - WITH 7% VAX

Expenses Date 2 (2024-01-16):
  3. Item C: 2,000 THB - NO TAX
  4. Item D: 1,500 THB - WITH 7% VAT
```

**Expected Results**:
```
✓ 4 Bills Created (2 dates × 2 VAT statuses)

Bill 1: ABC Supplies - Date: 2024-01-15 (No VAT)
  Item A: 1,000 THB

Bill 2: ABC Supplies - Date: 2024-01-15 (With VAT)
  Item B: 500 + 35 VAT

Bill 3: ABC Supplies - Date: 2024-01-16 (No VAT)
  Item C: 2,000 THB

Bill 4: ABC Supplies - Date: 2024-01-16 (With VAT)
  Item D: 1,500 + 105 VAT
```

**Test Steps**:
1. [ ] Create expenses with different dates
2. [ ] Verify date respected in bills
3. [ ] Verify 4 separate bills
4. [ ] Verify date shown in each bill reference

---

### Test Case 4: All Expenses WITHOUT VAT (No Separation Needed)

**Objective**: Verify single bill when all have same VAT status

**Setup**:
```
Employee: Staff D
Vendor: ABC Supplies

All expenses WITHOUT TAX:
  1. Item A: 1,000 THB
  2. Item B: 500 THB
  3. Item C: 2,000 THB
```

**Expected Results**:
```
✗ is_auto_mode = FALSE
  Reason: Single vendor, all with same VAT status

✗ vendor_summary = "" (empty)

✓ After Approval: 1 Bill Created

Bill 1: ABC Supplies - Date: 2024-01-XX (No VAT)
  Total: 3,500 THB
```

**Test Steps**:
1. [ ] Create Expense Sheet with all non-VAT items
2. [ ] Verify `is_auto_mode` = FALSE
3. [ ] Verify vendor_summary is empty
4. [ ] Click "Approve"
5. [ ] Verify only 1 bill created

---

### Test Case 5: All Expenses WITH VAT (No Separation Needed)

**Objective**: Verify single bill when all have VAT

**Setup**:
```
Employee: Staff E
Vendor: ABC Supplies

All expenses WITH 7% TAX:
  1. Item A: 1,000 THB
  2. Item B: 500 THB
```

**Expected Results**:
```
✗ is_auto_mode = FALSE
  Reason: Single vendor, all with same VAT status

✓ After Approval: 1 Bill Created

Bill 1: ABC Supplies - Date: 2024-01-XX (With VAT)
  Total: 1,500 + 105 VAT
```

**Test Steps**:
1. [ ] Create all VAT expenses
2. [ ] Verify `is_auto_mode` = FALSE
3. [ ] Click "Approve"
4. [ ] Verify 1 bill with (With VAT) label

---

### Test Case 6: Multiple Vendors WITHOUT Mixed VAT

**Objective**: Verify existing vendor separation still works

**Setup**:
```
Employee: Staff F

Vendor A (no VAT):
  Item 1: 1,000 THB

Vendor B (no VAT):
  Item 2: 2,000 THB
```

**Expected Results**:
```
✓ is_auto_mode = TRUE
  Reason: Multiple vendors

✓ vendor_summary:
  "🤖 AUTO MODE - แยกบิลตาม: Vendors: Vendor A, Vendor B"
  (Note: No VAT types shown because all have same status)

✓ After Approval: 2 Bills Created

Bill 1: Vendor A - Date: 2024-01-XX (No VAT)
Bill 2: Vendor B - Date: 2024-01-XX (No VAT)
```

**Test Steps**:
1. [ ] Create expenses for multiple vendors (same VAT)
2. [ ] Verify `is_auto_mode` = TRUE
3. [ ] Verify vendor_summary shows vendors
4. [ ] Click "Approve"
5. [ ] Verify 2 bills created (existing behavior preserved)

---

### Test Case 7: Employee Expenses (No Vendor)

**Objective**: Verify separation works for employee-paid expenses

**Setup**:
```
Employee: Staff G
NO VENDOR (employee pays)

Expenses:
  1. Meal: 500 THB - NO TAX
  2. Transport: 300 THB - WITH 7% VAT
```

**Expected Results**:
```
✓ is_auto_mode = TRUE
  Reason: Mixed VAT

✓ vendor_summary:
  "🤖 AUTO MODE - แยกบิลตาม: Employee: Staff G | Bill Types: 📊 With VAT | 📄 Without VAT"

✓ After Approval: 2 Bills Created

Bill 1: Employee: Staff G - Date: 2024-01-XX (No VAT)
  Meal: 500 THB

Bill 2: Employee: Staff G - Date: 2024-01-XX (With VAT)
  Transport: 300 + 21 VAT
```

**Test Steps**:
1. [ ] Create employee expenses without vendor
2. [ ] Verify employee name in summary
3. [ ] Click "Approve"
4. [ ] Verify 2 bills with employee name

---

### Test Case 8: Mixed Vendors & Employees & VAT

**Objective**: Comprehensive test with all variations

**Setup**:
```
Employee: Manager H

Line 1: Vendor ABC, 1,000 THB, NO VAT
Line 2: Vendor ABC, 500 THB, WITH VAT
Line 3: Vendor XYZ, 2,000 THB, NO VAT
Line 4: Vendor XYZ, 1,500 THB, WITH VAT
Line 5: No Vendor, 300 THB, NO VAT
Line 6: No Vendor, 200 THB, WITH VAT
```

**Expected Results**:
```
✓ is_auto_mode = TRUE

✓ vendor_summary:
  "🤖 AUTO MODE - แยกบิลตาม: Vendors: ABC, XYZ | Employee: Manager H | Bill Types: 📊 With VAT | 📄 Without VAT"

✓ After Approval: 6 Bills Created

Bill 1: ABC - Date: 2024-01-XX (No VAT)
  1,000 THB

Bill 2: ABC - Date: 2024-01-XX (With VAT)
  500 + VAT

Bill 3: XYZ - Date: 2024-01-XX (No VAT)
  2,000 THB

Bill 4: XYZ - Date: 2024-01-XX (With VAT)
  1,500 + VAT

Bill 5: Manager H - Date: 2024-01-XX (No VAT)
  300 THB

Bill 6: Manager H - Date: 2024-01-XX (With VAT)
  200 + VAT
```

---

## 🔍 Validation Checks

For each test case, verify:

- [ ] `is_auto_mode` value matches expectation
- [ ] `vendor_summary` displays correct information
- [ ] Correct number of bills created
- [ ] Bill references include correct VAT labels
- [ ] Line items distributed to correct bills
- [ ] VAT amount calculated correctly (where applicable)
- [ ] Partner (vendor/employee) correct on each bill
- [ ] Date respected in bill reference
- [ ] Bill totals match expense totals

---

## 📊 Data Validation

After bill creation, verify:

### Bill Header Fields
- [ ] `move_type` = 'in_invoice'
- [ ] `partner_id` correct
- [ ] `invoice_date` = expense line date
- [ ] `date` = expense line date
- [ ] `ref` includes VAT label
- [ ] `currency_id` correct

### Bill Line Items
- [ ] Correct expenses included
- [ ] Quantity and amount correct
- [ ] Tax IDs included correctly
- [ ] Account assignment correct
- [ ] Analytic distribution preserved

### Bill Links
- [ ] Bill linked to Expense Sheet via `expense_sheet_id`
- [ ] Advance Box linked via `advance_box_id`
- [ ] `is_expense_advance_bill` = TRUE

---

## ✅ Regression Testing

Verify existing functionality still works:

- [ ] Normal (non-mixed) vendor bills still created correctly
- [ ] Single vendor, single VAT status → single bill
- [ ] Multiple vendors without mixed VAT → multiple bills per vendor
- [ ] Advance box clearing still works with split bills
- [ ] WHT integration works with all bill variants
- [ ] Payment/reconciliation logic unaffected
- [ ] Report generation unaffected

---

## 📈 Performance Testing

- [ ] Bill creation time acceptable (< 5 seconds for 100 lines)
- [ ] UI load time acceptable
- [ ] No database query N+1 issues
- [ ] Audit logs/chatter updates properly
- [ ] Email notifications (if configured) sent correctly

---

## 🐛 Edge Cases to Test

- [ ] Empty expense sheet
- [ ] Single expense with VAT
- [ ] Single expense without VAT
- [ ] Very large expense amounts
- [ ] Multiple currencies (if configured)
- [ ] Zero-amount expenses
- [ ] Negative amounts (returns)

---

## 📋 Test Report Template

```
Test Case: [NUMBER] - [TITLE]
Date: [DATE]
Tester: [NAME]

Environment:
  - Odoo Version: 17.0
  - Module Version: 17.0.1.0.6
  - Python Version: [VERSION]

Setup:
  [Describe test setup]

Steps Executed:
  1. [Step 1]
  2. [Step 2]
  3. [Step 3]

Expected Results:
  [Expected outcome]

Actual Results:
  [What happened]

Status: [ ] PASS [ ] FAIL [ ] BLOCKED

Issues Found:
  [Any issues]

Comments:
  [Additional notes]
```

---

## 🎯 Sign-Off Criteria

Feature is ready for production when:

- [x] All test cases pass
- [x] No regressions in existing functionality
- [x] Performance acceptable
- [x] Edge cases handled
- [x] Documentation complete
- [x] Code review approved
- [x] User acceptance testing passed

---

## 📞 Support Contacts

- **Developer**: [Name]
- **QA Lead**: [Name]
- **Product Owner**: [Name]

---

**Testing Framework**: Odoo 17.0 Test Suite
**Status**: Ready for Testing
**Last Updated**: 2024-01-12
