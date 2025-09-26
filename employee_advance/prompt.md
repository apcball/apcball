You are an Odoo 17 developer.
Goal

Implement a custom "Clear with Advance" button on Vendor Bills created from employee expenses.

Keep Advance Account (141101) as Current Asset (account type = asset_current).

Standard Odoo "Register Payment" behavior remains unchanged (still limited to Payable/Receivable).

Only the Clear with Advance button bypasses that restriction:

It opens the Register Payment wizard.

Default payment journal = the employee’s Advance Box Journal.

Payment reconciles with the bill using Advance account.

Requirements
1) Extend Vendor Bill (account.move)

Add button Clear with Advance (visible when: move_type = in_invoice, state = posted, partner = employee/vendor, residual > 0).

Button action:

Calls account.payment.register wizard.

Context includes:

active_model = 'account.move'

active_ids = [bill.id]

force_advance_payment = True

default_advance_box_id = employee.advance.box.id

2) Detect Employee Advance Box

Link Advance Box (employee.advance.box) to employee via address_home_id.

When button pressed:

Auto-detect box of that employee.

Use box.journal_id as default journal_id for payment wizard.

If no box found → raise clear error:
"No Advance Box configured for this employee."

3) Override Payment Wizard (account.payment.register)

Inherit model.

In default_get or @api.model_create_multi:

If context force_advance_payment=True:

Accept Current Asset accounts as eligible lines (not only Receivable/Payable).

Auto-fill journal_id from context['default_advance_box_id'].journal_id.

Ensure partner is employee’s partner.

Do not change behavior if force_advance_payment=False.

4) Accounting Entries (Example)

Vendor Bill posted:

Dr Expense 10,000

Dr VAT 700

Cr AP (Vendor) 10,700

Cr WHT Payable 300

Clear with Advance (via Register Payment):

Dr AP (Vendor) 10,700

Cr 141101 Advance (Employee) 10,700

Result: Bill reconciled as Paid, Advance Box reduced.

5) UX/Validation

Wizard must show:

Advance Box auto-selected.

Default journal = Advance Box journal.

Amount = bill residual.

If no Advance Box found for employee: raise error and block.

Keep check printing available via payment wizard.

Acceptance Criteria

Clear with Advance button opens Register Payment wizard, even when advance account type = Current Asset.

Advance Box is auto-detected and pre-filled.

On confirmation, payment posted with Dr AP / Cr Advance (141101).

Vendor Bill marked Paid (reconciled).

Standard Register Payment (outside this button) remains unchanged (Receivable/Payable only).

Errors handled: missing Advance Box, no journal, locked period.

Works with multi-company, multi-currency, and WHT/VAT flows.

👉 With this, accountants keep Advance = Current Asset, while still enjoying the Register Payment workflow (audit trail + check printing) when clearing advances.