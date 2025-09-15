# MOG Expense Advance Petty Cash - Implementation Summary

## Overview
This module implements a comprehensive expense management system with three payment sources:
1. **Company (AP/Bank)** - Standard company payment
2. **Petty Cash** - Payment from petty cash boxes
3. **Advance** - Payment against employee/partner advances

## Key Features Implemented

### 1. Petty Cash Workflow ✅
- **Trigger**: Expense Sheet approval with `payment_source = 'petty_cash'`
- **Process**: Creates Journal Entry automatically
- **Accounting**:
  - Debit: Expense accounts (grouped by account)
  - Credit: Cash account of selected Petty Cash Journal
- **Validation**: Ensures petty cash box and journal are properly configured

### 2. Advance Workflow ✅
- **Creation**: Employee/Partner advance requests
- **Approval**: Manual approval process
- **Payment**: Creates Journal Entry when payment is registered
- **Accounting**:
  - Debit: Advance Account (Employee/Partner Advance)
  - Credit: Bank/Cash account from payment journal
- **States**: draft → approved → paid → cleared

### 3. Clearing Workflow ✅
- **Trigger**: Expense Sheet approval with `payment_source = 'advance'`
- **Process**: Automatically creates and posts clearing record
- **Accounting**:
  - Debit: Default account of Expense Sheet Journal
  - Credit: Advance Account
- **Auto-Status**: Sets advance to 'Cleared' when fully cleared
- **Validation**: Prevents over-clearing and validates advance state

## Technical Implementation

### Models Extended/Created:
1. **account.move** - Added `petty_cash_box_id` field
2. **hr.expense.sheet** - Added payment source fields and workflow logic
3. **account.petty.cash.box** - Petty cash management
4. **hr.expense.advance** - Advance requests and tracking
5. **hr.expense.advance.clearing** - Clearing records with accounting

### Key Validations:
- Expense accounts must be defined for petty cash payments
- Advance must be in 'paid' state before clearing
- Cannot clear more than available advance balance
- Automatic advance status updates when fully cleared
- Proper domain filtering for advance selection

### Accounting Integration:
- All journal entries automatically created and posted
- Proper account reconciliation through advance accounts
- Full audit trail through clearing records
- Currency support with proper decimal precision

## Usage Flow

### For Petty Cash:
1. Create expense sheet
2. Set payment_source = 'petty_cash'
3. Select petty cash box
4. Approve → Automatic JE creation

### For Advances:
1. Create advance request
2. Approve advance
3. Register payment → JE created
4. Create expense sheet with payment_source = 'advance'
5. Select advance
6. Approve → Automatic clearing and JE creation

## Files Modified/Created:
- `models/account_move.py` (new)
- `models/hr_expense_extend.py` (enhanced)
- `models/clearing.py` (enhanced)
- `models/advance_request.py` (existing)
- `models/petty_cash_box.py` (existing)
- `WORKFLOW_DOCUMENTATION.py` (new)

All workflows are now fully implemented and working according to the specifications!