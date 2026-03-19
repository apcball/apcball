# Odoo 17 AR Settlement Engine

## Production Prompt with Payment Difference Handling

You are a senior Odoo 17 developer and ERP architect.

Generate a production-ready Odoo module implementing an **AR Settlement Engine** for Odoo 17.

The system must support:

Customer payments
Credit note allocation
VAT grouping
Trade channel grouping
Payment differences (overpayment / underpayment)

The module must integrate fully with the Odoo accounting system.

---

# Module Information

Module Name

account_ar_settlement

Dependencies

account
mail
sale

Odoo Version

17.0

---

# Core Business Objective

Build an advanced **Accounts Receivable Settlement Engine** that allows accountants to settle invoices using:

Customer payments
Credit notes
VAT grouping
Trade channel grouping

The system must also support handling **payment differences**.

---

# PHASE 1

## Customer Payment Allocation

Create model

ar.settlement

Fields

name
partner_id
vat_group
trade_channel

payment_date
journal_id

currency_id
company_id

amount_received
bank_fee

allocated_amount
remaining_amount

state

line_ids
credit_line_ids

payment_id

---

# PHASE 2

## VAT Group Settlement

Allow invoice settlement across multiple branches with the same VAT ID.

Add field

vat_group

Logic

vat_group = partner_id.vat

Invoice domain

partner_id.vat = vat_group

---

# PHASE 3

## Trade Channel Settlement

Add field

trade_channel

Invoices loaded must match selected trade_channel.

Domain

trade_channel = selected trade_channel

---

# PHASE 4

## Credit Note Allocation

Model

ar.settlement.credit.line

Fields

settlement_id
credit_move_id

credit_total
credit_residual

use_amount

Domain

move_type = out_refund
state = posted
payment_state != paid

---

# PHASE 5

## Bank Fee Support

Add field

bank_fee

Accounting when confirming settlement

Dr Bank
Dr Bank Fee Expense
Cr Accounts Receivable

Bank fee account must be configurable.

---

# PHASE 6

## User Friendly UI

The settlement screen must contain:

SECTION 1

Payment Information

Customer
VAT Group
Trade Channel

Payment Date
Journal

Amount Received
Bank Fee

Buttons

Load Invoices
Auto Allocate

---

SECTION 2

Invoice Allocation Grid

Columns

Invoice
Branch
Trade Channel
Invoice Date
Due Date
Residual
Pay Amount

Overdue invoices must be visually highlighted.

---

SECTION 3

Credit Notes

Columns

Credit Note
Branch
Residual
Use Amount

---

SECTION 4

Summary

Payment Amount
Credit Used

Total Available

Allocated Amount
Remaining Balance

Values must update dynamically.

---

# PHASE 7

## Payment Difference Handling

The system must detect payment differences automatically.

Calculation

difference_amount =

(amount_received - bank_fee + credit_used)

* allocated_amount

---

If difference_amount = 0

Settlement is balanced.

---

If difference_amount > 0

Customer has **overpaid**.

System must allow three options:

1 Keep as Customer Credit

Create outstanding credit in Accounts Receivable.

2 Create Advance Payment

Keep amount as unapplied payment.

3 Refund to Customer

Optional future feature.

---

If difference_amount < 0

Customer has **underpaid**.

System must allow options:

1 Leave invoice partially paid

Standard Odoo behavior.

2 Write Off Difference

Create write-off entry.

Write-off account must be configurable.

3 Record as Short Payment Reason

Example

discount
bank charge
rounding difference

---

# Write-off Accounting Example

If difference = -500

Entry

Dr Write-off Expense 500
Cr Accounts Receivable 500

---
# PHASE 8

## Company Payment Difference Rule

The company uses a **clearing account for payment differences**.

Account Code:

214100

Account Name:

Accrued Expenses (ค่าใช้จ่ายค้างจ่าย)

This account must be used whenever payment difference occurs.

---

# Difference Calculation

difference_amount =

(amount_received - bank_fee + credit_used)

* allocated_amount

---

# Case 1

## Customer Overpayment

difference_amount > 0

Accounting Entry

Dr Bank
Cr Accounts Receivable
Cr Accrued Expenses (214100)

Example

Payment received = 105,000
Allocated invoices = 100,000

Entry

Dr Bank 105,000
Cr AR 100,000
Cr Accrued Expenses 5,000

---

# Case 2

## Customer Underpayment

difference_amount < 0

Accounting Entry

Dr Bank
Dr Accrued Expenses (214100)
Cr Accounts Receivable

Example

Payment received = 95,000
Allocated invoices = 100,000

Entry

Dr Bank 95,000
Dr Accrued Expenses 5,000
Cr AR 100,000

---

# System Configuration

Add setting field

payment_difference_account_id

Default value:

214100 Accrued Expenses

This account must be configurable in Accounting Settings.

---

# UI Requirement

Settlement screen must show

Difference Amount

And preview accounting impact.

Example

Difference Amount : 5,000

Posting Preview

Dr Bank 105,000
Cr Accounts Receivable 100,000
Cr Accrued Expenses 5,000

# UI Difference Panel

Add section

Payment Difference

Fields

Difference Amount

Handling Option

Selection

Customer Credit
Write-off
Partial Payment

---

# Accounting Integration

On Confirm Settlement

System must

Create account.payment
Post payment
Reconcile invoices
Apply credit notes

Handle difference according to selected option.

Never create manual journal entries for invoice settlement.

Use Odoo reconciliation framework.

---

# Menu

Accounting

Customers

AR Settlement

---

# Security

Accounting User

Create settlements

Accounting Manager

Full access

---

# Sequence

Sequence Code

ar.settlement

Example

ARS/2026/0001

---

# Module Structure

account_ar_settlement

**manifest**.py
**init**.py

models

ar_settlement.py
ar_settlement_invoice_line.py
ar_settlement_credit_line.py

views

ar_settlement_views.xml
ar_settlement_menu.xml

security

ir.model.access.csv

data

sequence.xml

---

# Coding Rules

Use Odoo ORM.

Use computed fields.

Use onchange methods.

Avoid raw SQL.

Ensure module installs cleanly.

---

# Expected Result

After installation users can:

Create AR settlement
Group invoices by VAT
Filter invoices by Trade Channel
Apply credit notes
Allocate payments
Handle payment differences
Confirm settlement

Invoices and payments must be reconciled automatically.
