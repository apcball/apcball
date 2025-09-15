# -*- coding: utf-8 -*-
"""
MOG Expense Advance Petty Cash - Workflow Documentation

This module implements the following workflows:

1. PETTY CASH WORKFLOW
   - User creates expense sheet with payment_source = 'petty_cash'
   - Selects appropriate petty_cash_box_id
   - When expense sheet is approved → action_post_entries()
   - System creates Journal Entry:
     * Debit: Expense accounts (summed by account)
     * Credit: Cash account of Petty Cash Journal (deducted from cash box)

2. ADVANCE WORKFLOW
   - User creates Advance Request (hr.expense.advance)
   - Sets advance_account_id (e.g., Employee Advance / Partner Advance)
   - Sets journal_id (Bank/Cash account for payment)
   - User approves advance → action_approve()
   - User registers payment → action_register_payment()
   - System creates Journal Entry:
     * Debit: Advance Account
     * Credit: Bank/Cash account

3. CLEARING WORKFLOW
   - User creates expense sheet with payment_source = 'advance'
   - Selects advance_id to clear against
   - When expense sheet is approved → action_post_entries()
   - System creates Clearing record automatically and posts it
   - Clearing creates Journal Entry:
     * Debit: Default account of Expense Sheet Journal (represents total expense payment)
     * Credit: Advance Account
   - If advance is fully cleared → advance status becomes 'Cleared'

MODELS:
- account.petty.cash.box: Represents petty cash boxes
- hr.expense.advance: Advance requests for employees/partners
- hr.expense.advance.clearing: Clearing records linking advances to expense sheets
- hr.expense.sheet: Extended with payment_source field
- account.move: Extended with petty_cash_box_id field

WORKFLOW STATES:
- Advance: draft → approved → paid → cleared
- Clearing: draft → posted
- Expense Sheet: uses standard hr_expense states

ACCOUNTING INTEGRATION:
- All journal entries are automatically created and posted
- Proper account reconciliation through advance account
- Petty cash balance tracking through cash journal
- Full audit trail through clearing records
"""