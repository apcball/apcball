Goal
On Vendor Bills created for employee expenses (Option 1), add a button to clear the bill against the employee’s Advance Account (141101) by auto-creating a reclass journal entry and reconciling both sides.

Where

account.move with move_type='in_invoice' and partner = employee’s private address.

Optional: expose the same action on hr.expense.sheet if it references the bill.

Button
Label: Clear with Advance
Visible when:

Move is posted, amount_residual > 0

Partner has an advance box with account 141101

Company/journal not locked

Action (pseudo)

Read bill open residual on AP (sum of posted lines user_type_id.type == 'payable').

Determine advance account: advance_acc = advance_box.account_id (141101) for this employee/ company.

Create account.move (type entry) in same company:

Dr AP (partner=employee)   amount = open_residual
    Cr 141101 (partner=employee) amount = open_residual


Use a configurable journal (e.g., “Advance Clearing Journal”). Post it.

Reconcile:

AP debit from the new JE ↔ AP credit on the bill

141101 credit from the new JE will later reconcile with the top-up entry (Dr 141101 / Cr Bank) automatically or via manual matching.

Mark bill as Paid (if residual=0 after reconciliation).

message_post on bill with a link to the clearing JE.

Edge cases

If WHT is applied on bill: AP open amount is Net of WHT only if WHT module posts a separate liability (213xxx). Ensure reconciliation uses the bill’s residual (not total).

Multi-currency: set currency_id and amount_currency on JE lines based on bill currency/rate.

Locked periods: raise clear error.

No advance account configured: raise error.

If only part of the bill is to be cleared, support partial amount (wizard with editable clear_amount ≤ residual).

Acceptance Criteria

Clicking Clear with Advance on a posted bill creates a posted JE (Dr AP / Cr 141101) for the open residual and reconciles AP → bill becomes Paid.

VAT report (l10n_th_account_tax) and WHT certificate remain intact (since the bill is unchanged).

Works with partial residuals and multi-currency.

Proper errors for missing advance account, locked date, or zero residual.

Messages/audit trail added; smart button to view the clearing JE.

Optional UX

Wizard bill.clear.advance.wizard → shows: bill residual, advance account, journal, amount (editable), memo.

Checkbox “Mark Expense Sheet Paid” if the bill originated from a sheet → call sheet.action_sheet_paid() after success.

Smart button “Clearing Entries” on the bill to list related JEs.

Security

Restrict button to group_account_user and above.