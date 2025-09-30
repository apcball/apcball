You are implementing a new feature in the custom module buz_account_receipt for Odoo 17.
The goal is to extend the Receipt model so that users can register batch payments directly from the Receipt form.

Reference module: Use Odoo’s standard account_payment_batch_process module as inspiration and technical reference. This ensures the design is consistent with existing batch payment handling in Odoo.

Requirements:
	1.	Add a new button “Register Batch Payment” on the Receipt form view.
	•	It should appear in the header, next to “Post” or “Cancel”.
	2.	When the button is clicked:
	•	Collect all invoices linked to the current Receipt (buz.account.receipt.line.move_id).
	•	Validate that:
	•	All invoices are posted.
	•	They belong to the same partner.
	•	They are customer invoices/refunds (out_invoice / out_refund).
	•	Their payment_state is in (not_paid, partial, in_payment).
	•	If validation fails, raise a clear UserError.
	3.	If validation passes:
	•	Open the standard account.payment.register wizard, but pre-populate it with:
	•	active_model = 'account.move'
	•	active_ids = [all invoice ids from receipt]
	•	Default partner = Receipt partner
	•	Default payment type = inbound
	•	Default communication = “Receipt ”
	4.	After the payment is confirmed in the wizard, link the generated account.payment records back to the Receipt (buz_receipt_id field).
	5.	Ensure compatibility with account_payment_batch_process module:
	•	If that module is installed, allow the receipt batch payment action to leverage its grouping/processing logic (e.g. multiple payments grouped into one batch).
	•	If not installed, fallback to the normal multi-invoice register payment flow.

Deliverables:
	•	Python: Add method action_register_batch_payment() in buz.account.receipt.
	•	XML: Add a smart-button or header button on the form view.
	•	Security: Ensure users with invoice/payment rights can execute the action.
	•	Documentation: Update README to explain the new “Batch Payment from Receipt” feature.