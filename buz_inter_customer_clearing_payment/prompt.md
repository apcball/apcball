# PROMPT: Odoo 17 Inter-Customer Clearing Payment with Credit Note (Unified Source)

You are a senior Odoo 17 Accounting & ERP developer.
Create a full custom module for Odoo 17 (Community / Enterprise compatible).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MODULE NAME
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
buz_inter_customer_clearing_payment

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MODULE PURPOSE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Create an accounting-grade module that allows users to:
- Use customer payments AND credit notes as unified settlement sources
- Allocate those sources to invoices of the same or different customers
- Apply inter-customer clearing logic automatically when partners differ
- Remain fully compliant with accounting principles and audit requirements

The module MUST support:
- Partial allocation
- Multi-currency (FX)
- Cancel (undo)
- Reverse (period closed)
- Payment + Credit Note combined allocation

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BUSINESS CONSTRAINTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Each branch is a separate customer (res.partner)
- Master data cannot be changed
- AR Aging must remain correct
- No direct reconciliation across different partners
- No manual journal manipulation by users

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
USER EXPERIENCE (UX FLOW)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Menu:
Accounting → Customers → Receive Clearing Payment

Wizard Steps:
1. Select Settlement Sources
2. Allocate to Target Invoices
3. Review & Confirm

Users must NOT manually reconcile journal items.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 1: SELECT SETTLEMENT SOURCES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Allow user to select multiple credit sources:

Source Types:
- Customer Payments (account.move, move_type = 'outbound payment')
- Customer Credit Notes (account.move, move_type = 'out_refund')

Fields shown per source:
- Select (Boolean)
- Type (Payment / Credit Note)
- Reference
- Customer
- Date
- Currency
- Available Amount (amount_residual > 0)

Source Domain:
- state = 'posted'
- amount_residual > 0

Total Available Credit = sum(selected sources)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 2: ALLOCATE TO TARGET INVOICES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Allow user to allocate available credit to invoices.

Invoice Fields:
- Select (Boolean)
- Invoice Number
- Customer
- Branch (analytic account or branch_id)
- Invoice Date
- Currency
- Residual Amount
- Allocate Amount (editable)

Invoice Domain:
- move_type = 'out_invoice'
- state = 'posted'
- payment_state in ('not_paid', 'partial')

Summary Bar:
- Total Available Credit
- Total Allocated
- Remaining Credit

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VALIDATION RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Allocation amount >= 0
- Allocation amount <= invoice residual
- Total allocated <= total available credit
- At least one allocation line required
- Currency conversion handled by Odoo (do not calculate manually)

Raise UserError with clear messages when validation fails.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ACCOUNTING LOGIC (CRITICAL)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Concept:
- Payment and Credit Note are both CREDIT sources in AR
- Invoices are DEBIT targets in AR
- Clearing journal entries are required when partners differ

──────────────
FOR EACH ALLOCATION LINE:
──────────────

Case 1: Source Partner == Invoice Partner
- Direct partial reconciliation between source AR line and invoice AR line

Case 2: Source Partner != Invoice Partner
1. Create a CLEARING journal entry:
   - Debit AR (invoice partner)
   - Credit AR (source partner)
   - Amount = allocated amount
   - Currency = invoice currency
   - Let Odoo generate balance / FX difference

2. Reconcile:
   - Invoice AR line ↔ Clearing AR (invoice partner)
   - Source AR line ↔ Clearing AR (source partner)

──────────────
DO NOT:
──────────────
- Reconcile AR lines of different partners directly
- Modify journal entries manually
- Compute FX manually
- Use SQL

Use account.partial.reconcile for all reconciliations.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MULTI-CURRENCY (FX) SUPPORT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Use original currency on source and invoice
- Clearing entries use invoice currency
- Odoo must automatically:
  - Compute balance
  - Create exchange difference entries
- FX difference must reverse correctly on reverse operation

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CANCEL & REVERSE BEHAVIOR
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Cancel (period open):
- Unreconcile all related reconciliations
- Cancel clearing journal entries
- Do NOT delete credit notes or payments
- Restore residual amounts correctly

Reverse (period closed):
- Reverse clearing journal entries
- Reverse payment if required
- Credit notes are NOT reversed automatically
- All FX differences must reverse correctly

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DATA MODELS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Wizard:
- model: buz.clearing.settlement.wizard
- fields:
  - source_line_ids (One2many)
  - allocation_line_ids (One2many)

Source Line (Transient):
- model: buz.clearing.source.line
- fields:
  - wizard_id
  - move_id (payment or credit note)
  - partner_id
  - currency_id
  - available_amount

Allocation Line (Transient):
- model: buz.clearing.allocation.line
- fields:
  - wizard_id
  - invoice_id
  - invoice_partner_id
  - branch_id
  - residual_amount
  - allocate_amount
  - currency_id

Persistent Link Model (REQUIRED):
- model: buz.clearing.link
- fields:
  - source_move_id
  - invoice_id
  - clearing_move_id
  - amount
  - reconcile_ids

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MODULE STRUCTURE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

buz_inter_customer_clearing_payment/
├── __manifest__.py
├── models/
│   ├── __init__.py
│   ├── clearing_engine.py
│   ├── clearing_link.py
│   └── account_move_extension.py
├── wizard/
│   ├── __init__.py
│   ├── clearing_wizard.py
│   ├── source_line.py
│   └── allocation_line.py
├── views/
│   ├── clearing_menu.xml
│   ├── clearing_wizard_views.xml
│   └── account_move_views.xml
├── security/
│   └── ir.model.access.csv
└── README.md

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TECHNICAL CONSTRAINTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Odoo version: 17.0
- Python 3.10+
- Follow Odoo ORM and accounting best practices
- No core modification
- Clean, commented, production-ready code
- Fully reversible and auditable

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DELIVERABLE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Generate:
- All Python models
- Wizard logic
- XML views (wizard + menu)
- Manifest file
- Security access
- README.md explaining:
  - Business scenario
  - Accounting logic
  - Cancel / Reverse behavior

Code must be installable and runnable in Odoo 17.
