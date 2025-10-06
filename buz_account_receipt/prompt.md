Implement: AR Receipts, AR Receipt Voucher (multi-customer), and AP Payment Voucher (multi-vendor) for Odoo 17

You are an Odoo 17 developer. Implement a set of accounting documents to control grouped receipts/payments with clean separation of concerns:

AR Receipt (account.receipt) = grouped proof for invoices of one customer (what Ball already has; refine as below).

AR Receipt Voucher (account.receipt.voucher, “RV”) = control document that can include multiple AR Receipts possibly from different customers, and when confirming it creates multiple inbound payments (one per partner).

AP Payment Voucher (account.payment.voucher, “PV”) = control document that can include multiple vendor bills from multiple vendors, and when confirming it creates multiple outbound payments (one per partner) with optional WHT.

Keep everything multi-company safe, support signed amounts for refunds & multi-currency, and keep batch payments constrained to one partner per payment (Odoo limitation) while allowing the control document to span many partners.

1) AR Receipt (refinement of existing buz_account_receipt)

Model: account.receipt and account.receipt.line (reuse/extend).

Selection: From Invoices list view → action “Create Receipt”.

Filter: move_type in ('out_invoice','out_refund'), state='posted', same partner, same company. (Optional config: enforce same currency.)

Line fields:

move_id

amount_total_signed (related)

amount_residual_signed (related)

amount_paid_to_date = amount_total_signed - amount_residual_signed (computed)

amount_to_collect (default = residual, editable)

Header computed:

receipt_total = sum(amount_to_collect)

Posting:

Config param buz.receipt_autopost (default true). If true → post on create; else manual post with sequence REC/%(year)s/%(seq)s.

Batch Payment button:

Button “Register Batch Payment” → open standard account.payment.register with only unpaid invoices from lines (residual > 0), active_model='account.move', active_ids=moves.ids, set default_communication=f"Receipt {name}".

Menu/Navigation:

Customers → Receipts (tree/form).

Report:

QWeb report_account_receipt: columns [Invoice, Date, Amount, Paid-to-Date, To Collect, Residual After Payment], totals for This Payment vs Cumulative Paid.

2) AR Receipt Voucher (new control doc) — multi-customer aggregator

Purpose: A control document that aggregates one or more AR Receipts which may belong to different customers. When confirming, it splits into multiple inbound payments (one per partner).

Models:

account.receipt.voucher

account.receipt.voucher.line

Header:

company_id (required), currency_id (related to company, or config to enforce single currency), date, note, state in ('draft','confirmed'), name (sequence RV/%(year)s/%(seq)s).

Totals (computed): amount_total = sum of line amounts (see below).

Lines:

receipt_id (m2o to account.receipt)

partner_id (related from receipt)

amount_to_receive (default = sum of amount_to_collect of that receipt, editable)

(Optional) reference to included invoice moves for traceability.

Confirm / Register Payments:

Button “Register Payments”:

Group lines by partner_id.

For each partner group:

Collect all underlying invoices that are still unpaid from the referenced receipts.

Determine amount to receive for this partner (sum of that partner’s portion).

Create one inbound account.payment per partner (or use account.payment.register programmatically) with:

payment_type='inbound', partner_type='customer', partner_id, amount=<sum partner amount>, date = voucher.date, ref = "RV {name}".

Post the payment, reconcile with the partner’s invoices covered by this voucher (respect signs for refunds).

After all partner payments are created, set voucher state='confirmed'.

Constraints:

Cannot cross company.

Recommended: enforce single currency per voucher (config).

Menu/Navigation:

Accounting (or Cash) → Receipt Vouchers (tree/form).

Report:

QWeb report_account_receipt_voucher: columns [Receipt No, Customer, Amount (This Voucher), Remark], show total, and a footer note: “This voucher generates one payment per customer.”

3) AP Payment Voucher (new control doc) — multi-vendor with WHT

Models:

account.payment.voucher (PV)

account.payment.voucher.line

Header:

company_id, currency_id (company-related or enforce single currency), date, note, state in ('draft','confirmed'), name (sequence PV/%(year)s/%(seq)s).

Computed totals: amount_total_gross, amount_total_wht, amount_total_net.

Lines:

partner_id (vendor)

move_id (bill/refund; domain: state='posted', move_type in ('in_invoice','in_refund'))

Monetary (use signed fields for correctness):

amount_total_signed (related)

amount_residual_signed (related)

amount_to_pay_gross (default = residual, editable)

WHT fields (Thailand):

wht_tax_id (domain to purchase WHT taxes; assume module adds is_wht=True or use tags)

wht_base_amount (default = amount_to_pay_gross, editable)

wht_rate (read from tax or config)

wht_amount = wht_base_amount * rate

amount_to_pay_net = amount_to_pay_gross - wht_amount

Create/Populate:

From Vendors → Bills list view: action “Create Payment Voucher” → prefill lines for selected posted bills, set gross= residual, prefill WHT from bill/config.

Register Payments (Outbound):

Button “Register Payments”:

Group lines by partner_id.

For each partner, total net = sum(amount_to_pay_net).

Create one outbound account.payment per partner:

payment_type='outbound', partner_type='supplier', partner_id, amount=<net>, date = pv.date, ref = "PV {name}", journal_id from config.

Post and reconcile with underlying vendor bills (respect refunds).

For lines with WHT:

Create journal entries for WHT (credit WHT payable, debit A/P or as per local CoA).

Create WHT certificates using l10n_th_account_wht_cert_form (if installed): map partner, base, rate, tax amount, reference to payment and PV. Provide a config switch to auto-generate vs manual.

Set PV state='confirmed' after success.

Report:

QWeb report_account_payment_voucher: columns [Vendor, Bill, Date, Gross, WHT%, WHT Amt, Net Pay]; totals (Gross, WHT, Net). Include payment method placeholders (transfer/check), signature blocks.

4) Common Requirements

Sequences:

AR Receipt: REC/%(year)s/%(seq)s

AR Receipt Voucher: RV/%(year)s/%(seq)s

AP Payment Voucher: PV/%(year)s/%(seq)s

Security:

Access for Accounting Users/Managers only; record rules to forbid cross-company access.

Menus/Actions/Views:

Customers → Receipts (AR)

Accounting/Cash → Receipt Vouchers (AR control)

Vendors → Payment Vouchers (AP control)

Config parameters (in ir.config_parameter or settings panel):

buz.receipt_autopost (bool) — default true.

buz.enforce_single_currency_per_voucher (bool) — default true.

buz.default_bank_journal_id for PV payments.

buz.auto_generate_wht_cert (bool) — default true.

Multi-currency & refunds:

Always use *_signed fields (total/residual) for displays and calculations to keep signs correct.

Validation: single company per document. Currency enforcement via config (if off, still display in company currency consistently).

Errors & UX:

If a selected invoice/bill has zero residual, exclude it from payment creation (show notice).

If after filtering there’s no payable/receivable content, block operation with a clear error.

On create from list view, enforce same partner & company for AR Receipt; allow many partners for RV and PV (since they split payments).

Reconciliation:

Use Odoo’s standard reconciliation via account.payment.register context or manual reconciliation API after payment post.

Chatter:

Log links to generated payments and (for PV) generated WHT certificates.

5) Technical Artifacts to Deliver

Python models for account.receipt.voucher & account.payment.voucher (+ line models).

Extensions to existing account.receipt to add amount_to_collect, totals, batch payment action, and optional autopost.

Server actions:

Invoices (customer) → “Create Receipt”

Receipts → “Register Batch Payment”

Receipts → “Add to Receipt Voucher” (optional)

Bills (vendor) → “Create Payment Voucher”

Views:

tree/form/search for Receipt, Receipt Voucher, Payment Voucher

buttons: Post/Confirm, Register Payments, Print

Data:

Sequences (REC, RV, PV)

Menus, actions, security access CSV

Reports:

QWeb reports: report_account_receipt, report_account_receipt_voucher, report_account_payment_voucher

Settings:

System parameters or a Settings panel for the configs above.

WHT integration (if l10n_th_account_tax & l10n_th_account_wht_cert_form present):

Compute WHT per PV line, create JE and certificates on confirm (guard with module availability & config).

6) Acceptance Criteria

AR Receipt creation from customer invoices (same partner/company) produces a posted (or draft per config) receipt with correct signed totals; batch payment opens standard wizard with only unpaid invoices.

AR Receipt Voucher accepts multiple receipts across customers, and on “Register Payments” creates one inbound payment per customer, posted and reconciled, then sets state=confirmed.

AP Payment Voucher accepts multiple vendor bills across vendors, computes Gross/WHT/Net per line, and on “Register Payments” creates one outbound payment per vendor, posts & reconciles; if WHT configured, creates WHT JEs and certificates for each affected line/vendor.

All documents are company-safe; optional single currency enforcement works.

QWeb prints show correct totals and columns; sequences REC/RV/PV apply.

Robust errors for empty selections / zero residual / cross-company violations.

Unit/integration tests (minimal):

AR Receipt totals and batch payment context.

RV grouping → multiple inbound payments created with correct amounts.

PV with WHT → correct net amounts, payments per vendor, and WHT artifacts when enabled.

Mixed refunds handled (negative signed) without assertion failures.