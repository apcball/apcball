# Odoo 17 Module Enhancement Prompt

## Target Module

Enhance the existing module:

buz_inter_customer_clearing_payment

Do NOT create a new standalone module.

Extend the existing module by adding **Batch Payment Allocation functionality** designed for retail payment settlement scenarios.

---

# Objective

Enhance the existing **Inter-Customer Clearing Payment module** to support **Batch Payment Allocation** where a single bank payment must be distributed across many invoices.

This scenario typically occurs when:

* Customers pay invoices individually using QR payments
* At the end of the day the bank transfers a **single lump sum**
* Accounting must allocate that payment across many invoices

The new feature must reuse the **existing clearing logic** already implemented in the module.

---

# Important Design Rule

The module already contains the core logic for:

* Creating payments
* Creating clearing journal entries
* Performing reconciliations
* Maintaining audit links

This enhancement must **reuse the existing clearing logic** instead of duplicating it.

If needed, refactor the clearing logic into a reusable service layer.

---

# New Feature: Batch Payment Allocation Wizard

Add a new wizard.

Model name:

buz.batch.payment.wizard

This wizard allows accounting users to:

1. Receive a lump-sum bank payment
2. Filter invoices
3. Automatically allocate payment across invoices
4. Apply bank fees
5. Record settlement differences
6. Automatically reconcile everything

---

# Menu

Add new menu:

Accounting
→ Customers
→ **Batch Payment Allocation**

---

# Wizard Step 1 — Settlement Information

Fields:

payment_date
journal_id
currency_id
received_amount
reference

vat
trade_channel
date_from
date_to

bank_charge
bank_fee_account_id

difference_amount
difference_account_id

Descriptions:

received_amount
Actual amount received from the bank.

bank_charge
Optional bank fee deducted by bank.

difference_amount
Manual settlement difference.

---

# Invoice Filtering

Invoices must be filtered using:

move_type = 'out_invoice'
state = 'posted'
payment_state in ('not_paid','partial')

Additional filters:

commercial_partner_id.vat = wizard.vat

trade_channel = wizard.trade_channel

invoice_date >= date_from
invoice_date <= date_to

---

# Step 2 — Invoice Allocation

Show invoice table.

Columns:

Invoice Number
Invoice Date
Customer
VAT
Trade Channel
Residual Amount
Allocated Amount
Selected

Users can manually edit allocation.

---

# Auto Allocation

Add button:

Auto Allocate

Allocation logic:

FIFO based on invoice_date.

Pseudo logic:

remaining = received_amount

for invoice in invoices.sorted(invoice_date):

```
if remaining <= 0:
    break

allocate = min(invoice.residual, remaining)

line.allocate_amount = allocate

remaining -= allocate
```

---

# Step 3 — Review

Display settlement summary:

Total Invoice Amount
Total Allocated
Bank Charge
Difference Amount
Remaining Balance

Validation rule:

allocated_total must equal

received_amount + bank_charge + difference_amount

---

# Payment Creation

Reuse the existing payment creation logic from the module.

Journal entry example:

Dr Bank
Dr Bank Fee Expense (optional)
Dr Difference Account (optional)
Cr AR (Clearing Customer)

The payment partner should be the selected clearing partner.

---

# Clearing Entries

Reuse the module's existing clearing entry logic.

For each allocated invoice where partner differs:

Dr AR (Invoice Customer)
Cr AR (Clearing Customer)

---

# Reconciliation

Reuse existing reconciliation methods.

Perform reconciliations using:

account.partial.reconcile

Reconcile pairs:

Invoice AR ↔ Clearing AR

Payment AR ↔ Clearing AR

Never reconcile directly across different partners.

---

# Data Model Extension

Extend existing model:

buz.clearing.link

Add optional fields:

trade_channel
invoice_date
settlement_batch

These fields improve reporting and traceability.

---

# Wizard Line Model

Create new transient model:

buz.batch.payment.line

Fields:

wizard_id
invoice_id
partner_id
invoice_date
residual
allocate_amount
selected
currency_id

---

# Cancel Support

Reuse the module's cancel logic.

If accounting period is open:

1. Unreconcile all related lines
2. Cancel clearing entries
3. Cancel payment

---

# Reverse Support

If period is closed:

Use standard Odoo reversal:

account.move.reversal

Reverse both:

* payment move
* clearing moves

---

# Performance Requirements

The wizard must support large invoice sets.

Use efficient searching instead of loading all invoices automatically.

Invoices should load only after user applies filters.

---

# Security

Allow access to:

account.group_account_user
account.group_account_manager

---

# Module Structure Update

Update the existing module structure:

buz_inter_customer_clearing_payment

Add:

wizard/batch_payment_wizard.py
wizard/batch_payment_line.py

Add new views:

views/batch_payment_wizard_view.xml

Add new menu:

views/batch_payment_menu.xml

---

# UX Requirements

Wizard should be simple for accountants.

Display clear totals:

Total Invoices
Allocated Amount
Remaining Balance

Highlight mismatches visually.

---

# Expected Result

Accounting users can:

1. Receive one lump-sum bank payment
2. Filter invoices by VAT and Trade Channel
3. Automatically allocate payment across many invoices
4. Apply bank charges
5. Record settlement differences
6. Automatically reconcile all invoices
7. Maintain full accounting audit trail

depend module sr_extra_bank_charges, marketplace_settlement