Prompt: Odoo 17 Module – Employee Advance Box + Draft Bill + Clear Advance + Standard Payment

Module Goal

Implement a full workflow for employee advances:
	•	Maintain Advance Box per employee (141101) with Refill-to-Base.
	•	Employees submit Expenses and tick “Clear from Advance” selecting a box.
	•	After Manager Approval, the system creates a Vendor Bill (draft) and assigns an Activity to Accounting (configurable).
	•	Accounting posts the bill.
	•	Accounting clicks “Clear Advance” to create a JE (Dr AP / Cr 141101) and reconcile.
	•	Payment proceeds via standard Register Payment (supports check printing).
	•	VAT/WHT reporting works via the Vendor Bill.

⸻

Data Model & Config

Models
	1.	employee.advance.box

	•	employee_id (m2o hr.employee)
	•	account_id (m2o account.account, default 141101)
	•	journal_id (m2o account.journal, bank/cash for top-ups/refunds)
	•	remember_base_amount (monetary) – base target for Refill
	•	balance (compute, posted lines on 141101 with employee partner: debit − credit)
	•	Chatter (audit)

	2.	hr.expense.sheet (inherit)

	•	use_advance (bool, default=True)
	•	advance_box_id (m2o employee.advance.box; domain by employee/company)
	•	bill_id (m2o account.move; created draft bill)
	•	payment_ids (m2m account.payment; audit/smart button)

	3.	res.config.settings

	•	Accounting Activity Settings for draft bill notification:
	•	advance_notify_user_id (m2o res.users) or advance_notify_group_id (m2o res.groups)
	•	advance_notify_activity_type_id (m2o mail.activity.type)
	•	advance_notify_deadline_days (int)
	•	advance_default_clearing_journal_id (m2o account.journal, type=general, for Dr AP / Cr 141101)

Wizards
	•	advance.refill.base.wizard – Refill-to-remembered base
	•	Shows current_balance, base_amount_ref, topup_amount
	•	On confirm: create JE Dr 141101 / Cr Bank and update remember_base_amount to new balance.

Security/Views
	•	Buttons visible to group_account_user/manager.
	•	Tree/form views for Advance Box; tabs on Expense Sheet for Bill/Payments; config page for notifications.

⸻

Business Flow

A) Refill Advance Box
	•	User opens Advance Box → click Refill to Base.
	•	Wizard computes topup_amount = max(base − current_balance, 0).
	•	Create posted JE:
	•	Dr 141101 (partner=employee)
	•	Cr Bank (journal.default_account_id)
	•	Post, log to chatter, update remember_base_amount.

B) Employee Expense (Clear from Advance)
	1.	Employee creates Expense lines and marks “Clear from Advance”, selects advance_box_id.
	2.	Manager Approval on hr.expense.sheet triggers:
	•	Create Vendor Bill (draft) move_type='in_invoice', partner = employee private address.
	•	Copy expense lines → invoice lines (accounts, taxes VAT/WHT-ready).
	•	Set sheet.bill_id.
	•	Create Activity (mail.activity) for Accounting per settings:
	•	To user/group, with type & deadline, referencing the bill.
	3.	Accounting reviews → Post the bill (standard Odoo).

C) Clear Advance (after Bill is Posted)
	•	On the posted bill (partner = employee), show button “Clear with Advance”.
	•	Action creates posted JE in clearing journal:
	•	Dr AP (employee) amount = bill residual
	•	Cr 141101 (employee) amount = bill residual
	•	Reconcile AP debit (JE) with AP credit (bill).
	•	Bill becomes Paid (if residual=0).
	•	Expense Sheet can call action_sheet_paid() (if linked) and log message.

D) Payment (normal)
	•	If bill still has residual (e.g., advance < bill):
	•	Accounting clicks Register Payment (standard) → choose bank/check, confirm → Print Check possible.
	•	Reconcile payment with AP.
	•	If advance > bill and company wants refund from employee:
	•	Record inbound payment (standard) or top-down policy to reduce future refill.

⸻

Accounting Entries (Examples)

Refill to Base (10,000 target; current 6,000 → top-up 4,000):
	•	Dr 141101 4,000 / Cr Bank 4,000

Draft Bill from Expense (10,000 + VAT 700; WHT 300 via Thai WHT module after post):
	•	Post Bill:
	•	Dr Expense 10,000
	•	Dr VAT Input 700
	•	Cr AP (Employee) 10,700
	•	(WHT module may add Cr WHT Payable 300 depending on configuration/step)

Clear with Advance (bill residual 10,700):
	•	Dr AP (Employee) 10,700
	•	Cr 141101 (Employee) 10,700
	•	Reconcile AP lines → Bill Paid (if no WHT net or after WHT handling)

Payment (if residual remains):
	•	Dr AP / Cr Bank (standard payment); Check printing supported.

VAT report (l10n_th_account_tax) and WHT certificate/PND 3/53 work off the Vendor Bill.

⸻

UI/UX Requirements
	•	Expense Sheet:
	•	Fields: use_advance, advance_box_id
	•	On Approve: create Bill (draft) + Activity to Accounting
	•	Smart buttons: Bill, Payments
	•	Vendor Bill:
	•	Button Clear with Advance (visible if partner=employee, posted, residual>0, box/account available)
	•	Logs link to created clearing JE
	•	Config:
	•	Page to set activity user/group/type/deadline, and default clearing journal.

⸻

Error Handling
	•	Missing employee private address (partner) → block with clear error.
	•	Missing 141101 account, bank journal default account, or clearing journal → block with clear error.
	•	Locked fiscal period → block posting, show error.
	•	Multi-company/currency supported (set company_id, currency_id, amount_currency properly, use bill rate).

⸻

Acceptance Criteria
	1.	Manager approval creates draft Vendor Bill and Accounting Activity as configured.
	2.	Posting the bill yields proper VAT lines; WHT module operates and can generate certificates.
	3.	Clear with Advance posts JE (Dr AP / Cr 141101) and reconciles AP; bill becomes Paid when residual zero.
	4.	Standard Register Payment flow works, including check printing.
	5.	Advance Box Refill-to-Base works and keeps remember_base_amount in sync.
	6.	Audit trail visible on Sheet, Bill, and Advance Box (messages, smart buttons).
	7.	Robust errors for missing accounts/partner/journals and locked periods.
