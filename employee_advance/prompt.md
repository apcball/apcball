Implement “Pay to Vendor per expense line” with auto bill-splitting:

1) Models:
   - hr.expense (line): add vendor_id (supplier), constraints to require when needed.
   - hr.expense.sheet: fields clear_mode (reimburse_employee | pay_vendor | mixed),
     bill_ids (m2m account.move), is_billed flag.

2) Bill creation (on manager approve or explicit button):
   - Group expense lines by (vendor_or_employee_partner, company, currency).
   - Create draft account.move (move_type='in_invoice') per group, copying taxes/analytic/accounts.
   - invoice_origin/ref = sheet.name; link all created bills back to sheet.bill_ids.
   - Carry attachments from expense lines to the corresponding bill/line.
   - Post an Accounting Activity to reviewers (configurable).

3) Clear with Advance:
   - On posted bills, provide a “Clear with Advance” button that opens account.payment.register
     with context force_advance_payment=True and default_journal_id=advance_box.journal_id.
   - Advance account is Current Asset (141101); only this button bypasses the default AR/AP check.
   - Payment results in Dr AP / Cr 141101 and reconciles the bill (Paid).
   - Normal Register Payment outside this button remains standard.

4) Batch:
   - Add a server action/wizard “Create Bills (by Vendor)” for multiple sheets; avoid duplicates using is_billed.

5) Validations:
   - Enforce company & currency consistency per group.
   - Require vendor_id for lines in pay_vendor/mixed mode.
   - Handle locked periods, missing partner private address (employee), missing advance box/journal.
   - Sequence safety: keep name='/' before posting and retry once on duplicate.

6) UX:
   - Smart buttons for Bills/Payments on sheets.
   - Wizard preview showing how many bills will be generated per vendor/employee.

7) Reports:
   - Ensure Thai VAT/WHT modules operate on the generated vendor bills (no JE-only flows).
