# Expense Line Separation Fix

## Problem
When users create expense reports with the same product code multiple times, the system was combining these expense lines into a single invoice line when creating vendor bills. This caused issues with tracking individual expenses.

**Example:**
- Expense 1: Product A, Amount 100 THB
- Expense 2: Product A, Amount 200 THB
- **Old behavior**: Created 1 invoice line with Product A, Amount 300 THB
- **New behavior**: Creates 2 separate invoice lines

## Solution
Modified the bill creation logic in `_create_single_bill_for_vendor_group_date()` method to include the expense line ID in the grouping key.

### Changes Made

#### File: `models/expense_sheet.py`

1. **Updated grouping key** (Line ~451):
```python
# OLD: Group by account, taxes, analytic, WHT, product only
key = (account.id, taxes, tuple(sorted(analytic_distribution.keys())), wht_tax, product_id)

# NEW: Include expense.id to ensure each expense line is separate
key = (account.id, taxes, tuple(sorted(analytic_distribution.keys())), wht_tax, product_id, expense.id)
```

2. **Updated loop to handle expense_id** (Line ~488):
```python
# OLD: 5 elements in tuple
for (account_id, taxes_tuple, analytic_keys, wht_tax, product_id), group_data in account_tax_groups.items():

# NEW: 6 elements in tuple (added expense_id)
for (account_id, taxes_tuple, analytic_keys, wht_tax, product_id, expense_id), group_data in account_tax_groups.items():
```

3. **Updated logic to handle single expense per group** (Line ~497-508):
```python
# Since each expense now has its own group (expense.id in key),
# there should only be one expense per group
if len(expense_lines) == 1:
    # Use the single expense details
    single_expense = expense_lines[0]
    line_vals['name'] = single_expense.name
    line_vals['quantity'] = single_expense.quantity
    line_vals['price_unit'] = self._calculate_expense_base_amount(single_expense)
else:
    # Fallback (shouldn't happen)
    line_vals['name'] = ', '.join(expense_lines.mapped('name'))
```

4. **Fixed attachment handling** (Line ~529-532):
```python
# Get all expenses from all groups to attach
all_expenses = self.env['hr.expense']
for group_data in account_tax_groups.values():
    all_expenses |= group_data['expenses']
self._carry_attachments_to_bill(all_expenses, bill)
```

#### File: `__manifest__.py`

Updated version and description:
- Version: `17.0.1.0.3` → `17.0.1.0.4`
- Added description: "Each expense line creates a separate invoice line (no grouping by product)"
- Added: "FIXED: Expense lines with same product code now remain separate in bills"

## Impact

### Benefits
✅ Each expense line maintains its own identity in the bill
✅ Better tracking of individual expenses
✅ Clearer audit trail for accounting
✅ Easier to match expense receipts with invoice lines
✅ No change to bill grouping by vendor and date

### Behavior
- Bills are still grouped by **vendor/employee** and **expense date**
- Within each bill, each expense line creates a **separate invoice line**
- Even if multiple expense lines use the **same product**, they remain separate
- All other grouping rules remain unchanged (partner, date, company, currency)

## Example Scenario

### Input: Expense Sheet
```
Employee: John Doe
Expense Lines:
1. Taxi - Product: Transportation, Amount: 100 THB, Date: 2024-01-15
2. Taxi - Product: Transportation, Amount: 150 THB, Date: 2024-01-15
3. Meal - Product: Food, Amount: 200 THB, Date: 2024-01-16
```

### Output: Bills Created

**Bill 1** (Date: 2024-01-15)
- Line 1: Taxi, 100 THB
- Line 2: Taxi, 150 THB

**Bill 2** (Date: 2024-01-16)
- Line 1: Meal, 200 THB

## Testing

To test this fix:
1. Create an expense sheet with multiple expense lines using the same product
2. Approve the expense sheet (to trigger bill creation)
3. Verify that each expense line creates a separate invoice line in the bill
4. Check that all expense details (amount, taxes, WHT) are correctly preserved

## Upgrade Notes

- This change is backward compatible
- Existing bills are not affected
- Only new bills created after upgrade will have separate lines
- No data migration required

## Version History
- **17.0.1.0.4** (Current): Fixed expense line grouping to prevent combining same products
- **17.0.1.0.3**: Previous version with product grouping
