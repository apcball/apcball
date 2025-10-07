You are an Odoo 17 developer. Improve the existing buz_account_receipt module (AR side) to make grouped receipts production-ready and RV-ready.

Goals

Keep account.receipt as a grouped receipt for one customer (from multiple invoices).

Make the receipt reflect “amount to collect this round”, not historical paid.

Enable batch payment from the receipt (unpaid only), and allow outstanding payment fallback if nothing is due.

Be RV-ready: expose helpers and relations so an external account.receipt.voucher (RV) can drive payments per customer.

Robust UX: clean validations, sequences, reporting, multi-currency, refunds.

Scope of Work
1) Models: account.receipt & account.receipt.line

Keep receipt partner/company one-to-one:

Enforce same partner, same company for all lines.

Optional config to enforce single currency.

Fields (header):

name (sequence REC/%(year)s/%(seq)s), company_id, partner_id, currency_id (related to company), date (default today), note, state in ('draft','posted').

amount_total (computed) = sum of line amount_to_collect.

Fields (line):

move_id (posted, out_invoice/out_refund), amount_total_signed (related), amount_residual_signed (related).

amount_paid_to_date = amount_total_signed - amount_residual_signed (computed).

amount_to_collect (monetary, default = residual, user-editable).

Computations:

Use *_signed amounts for proper sign and multi-currency.

Posting:

Add system param buz.receipt_autopost (default True). If true → assign sequence + set state=posted on create; else allow edit in draft.

2) Create from Invoice List (Server Action)

Action “Create Receipt” on customer invoices list:

Filters: state='posted', move_type in ('out_invoice','out_refund'), same partner & company.

Initialize lines with amount_to_collect = amount_residual_signed.

Respect config buz.receipt_autopost.

Return form view of the new receipt.

3) Batch Payment on Receipt

Header button: “Register Batch Payment”:

If there are unpaid invoices: open standard wizard account.action_account_payment_from_invoices with context:

active_model='account.move', active_ids=[invoice_ids with residual>0]

default_payment_type='inbound'

default_payment_date=receipt.date

default_communication=f"Receipt {receipt.name}"

If no unpaid invoices: open/create an on-account (outstanding) inbound payment for this partner:

Prefill partner_id, amount=receipt.amount_total, date=receipt.date, ref=f"Receipt {receipt.name}".

Post it and let the user reconcile later (or just open the payment form with defaults).

4) RV-Ready Hooks (Public Methods)

Add small, documented helpers so an external RV module can orchestrate payments cleanly:

receipt_get_unpaid_moves(self) -> account.move: return posted invoices in this receipt with residual > 0.

receipt_build_payment_context(self, journal_id=None, memo_suffix=None) -> dict: return standard context for account.payment.register.

receipt_link_payments(self, payments: account.payment): persist links for audit (see §5).

(Optional) receipt_reconcile_with_payment(self, payment: account.payment): auto-reconcile payment receivable line with receivable lines from underlying invoices (partial-friendly).

5) Traceability: Link to Payments

Add M2M on account.receipt (and/or lines) to payments:

payment_ids = fields.Many2many('account.payment', 'account_receipt_payment_rel', 'receipt_id','payment_id', readonly=True)

Computed payment_count on header.

Add smart button “Payments (N)” on the receipt form → open tree/form of linked payments.

When batch payment wizard completes (or on manual link via RV), call receipt_link_payments().

6) Validations & UX

Remove current restriction payment_state in ('paid','in_payment') from selection logic (it blocks batch payments).

During creation:

Block cross-company.

Enforce same partner.

(Config) Enforce single currency.

Disable “Register Batch Payment” if state != posted (when autopost off) or there’s literally nothing to collect and outstanding fallback is disabled (config)!

7) Configuration

buz.receipt_autopost (bool, default True).

buz.enforce_single_currency_per_receipt (bool, default True).

buz.default_bank_journal_id (int, nullable; used as default in payment context).

buz.allow_outstanding_fallback (bool, default True).

8) Reports (QWeb)

Update Receipt (PDF):

Header: Receipt No., Date, Customer, Company.

Table columns: Invoice, Date, Total, Paid-to-Date, To Collect (This Receipt), Residual After Payment (theoretical).

Totals: This Payment (sum amount_to_collect) and Cumulative Paid.

Footer: Payment method/memo placeholder.

Ensure multi-currency labels are consistent; display signs correctly for refunds.

9) Security, Menus, Actions

Keep menu under Customers → Receipts (tree, form, search).

Access: Accounting Users/Managers.

Add search filters: by partner, date, state, amount>0, has payments.

10) Tests (minimal but useful)

Create receipt from invoices (mixed invoice+refund) → check totals using signed amounts.

Batch payment:

With unpaid invoices → opens register wizard context with correct active_ids.

With no unpaid invoices & allow_outstanding_fallback=True → creates/opens on-account payment.

Linkage:

After creating payment(s), payment_count > 0 and smart button shows them.

Multi-currency:

Signed amounts are correct; no crash.

Autopost toggle:

When off, keep in draft → allow editing amount_to_collect → post → sequence assigned.

Acceptance Criteria

Creating a receipt from invoice list requires same partner & company, uses residual to set amount_to_collect, and posts immediately if buz.receipt_autopost=True.

Register Batch Payment includes only invoices with residual>0; otherwise opens/creates an outstanding inbound payment (config-controlled).

Receipts show a Payments smart button with the correct count and open the linked payments.

Public helper methods exist and are used successfully by an external RV module (no tight coupling).

QWeb shows “This Payment” totals from amount_to_collect and prints refund signs correctly using signed fields.

No cross-company creation; optional single-currency enforcement works.

Unit tests pass for the flows above.

Nice-to-Have (optional)

Add chatter logs when payments are linked/unlinked.

Add a “Duplicate receipt” action that re-pulls residuals (handy for re-issuing).

Add a constraint to prevent amount_to_collect > amount_residual_signed per line (with small tolerance).