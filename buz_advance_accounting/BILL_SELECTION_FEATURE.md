# Bill Selection Feature - Advance Accrual Wizard

## Overview
Enhanced the advance accrual wizard to support selecting from multiple vendor bills when creating advance accrual entries.

## Changes Implemented

### 1. Model Changes (`wizards/advance_bill_wizard.py`)

#### New Fields:
- **`available_bill_ids`**: Many2many field that stores all posted vendor bills linked to the PO
- **`bill_count`**: Integer field showing the number of available bills
- **`vendor_bill_id`**: Changed from readonly to selectable with domain restriction

#### New Methods:
- **`_compute_available_bills()`**: 
  - Finds all posted vendor bills linked to the PO
  - Searches via invoice lines (proper Odoo way)
  - Also checks custom `purchase_id` field
  - Combines results and removes duplicates
  - Updates `available_bill_ids` and `bill_count`

- **`_onchange_vendor_bill_id()`**:
  - Triggered when user selects a bill
  - Updates `amount` from selected bill's total
  - Updates `exchange_rate` from bill (manual rate if available, otherwise system rate)
  - Recomputes preview lines

#### Modified Methods:
- **`_onchange_purchase()`**: 
  - Simplified logic
  - When called from receipt and bills available: auto-selects first bill
  - When called from PO: clears bill selection and uses PO amount
  - Delegates amount/rate calculation to `_onchange_vendor_bill_id()`

### 2. View Changes (`wizards/advance_bill_wizard_views.xml`)

#### UI Improvements:
1. **Success Alert** (shown when bills found):
   - Shows bill count
   - Prompts user to select a bill

2. **Warning Alert** (shown when no bills found):
   - Informs user no bills available
   - Notes that PO amount and system rate will be used

3. **Bill Selection Section**:
   - Only visible when bills are available
   - Dropdown to select from available bills
   - Options: no_create (prevents creating new bills), no_open allows viewing selected bill

## User Experience

### Scenario 1: Single Bill
- Wizard auto-selects the only available bill
- User can see bill details and proceed

### Scenario 2: Multiple Bills
- Wizard shows "✓ X Bill(s) Found" message
- User selects desired bill from dropdown
- Amount and exchange rate update automatically when selection changes

### Scenario 3: No Bills
- Wizard shows warning message
- Uses PO amount and system exchange rate
- User can still create accrual entry manually

## Technical Details

### Bill Search Logic:
1. Search via `invoice_line_ids.purchase_line_id.order_id` (standard Odoo linking)
2. Fallback: Search via custom `purchase_id` field
3. Combine results with union operator (`|`) to remove duplicates
4. Order by date descending, then ID descending

### Exchange Rate Priority:
1. Manual rate from bill (if `is_exchange` and `rate` > 0)
2. System rate calculated from bill's currency conversion
3. Fallback to 1.0 if no conversion available

## Benefits
- **Flexibility**: Handle POs with multiple vendor bills
- **Accuracy**: Pull exact amounts and rates from specific bills
- **User Choice**: Let users decide which bill to use for accrual
- **Transparency**: Clear UI showing bill availability and selection

## Files Modified
- `/wizards/advance_bill_wizard.py` - Core logic
- `/wizards/advance_bill_wizard_views.xml` - UI layout
