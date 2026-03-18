# Inter-Customer Clearing Payment Module

## Overview

This module provides a user-friendly wizard to receive a customer payment and allocate that payment to invoices of multiple customers using inter-customer clearing logic, while remaining 100% accounting-correct and audit-safe.

## Business Scenario

- Customers are separated by branch (each branch = different customer record)
- One branch/customer sends a lump-sum payment
- That payment must be used to settle invoices of other branches/entities within the same corporate group
- Master data CANNOT be changed
- AR Aging and audit trail must remain correct

## Key Features

- **Multi-Branch & Corporate Group Support**: Automatically groups customers that share the same Tax ID (VAT).
- **User-Friendly 3-Step Wizard**: Intuitive interface with clear step-by-step guidance.
- **Smart Invoice Filtering**: When a paying customer is selected, the system strictly filters the available open invoices to only those belonging to customers with the exact same Tax ID.
- **Partial Payment Support**: Allocate exact or partial amounts to multiple invoices.
- **Multi-Currency Support**: Automatic FX handling by standard Odoo accounting logic.
- **Cancel & Reverse Functionality**: Full support for cancellation and reversal of the clearing payments.
- **Accounting-Correct & Audit-Safe**: All entries follow proper accounting principles without manual reconciliation.

## User Experience Flow

### Menu Location
Accounting → Customers → Receive Clearing Payment

### Wizard Steps

#### Step 1: Select Paying Customer
- Select a paying customer (Must be a company with a valid Tax ID).
- The system displays their Tax ID.
- Enter payment details (Journal, Date, Amount, Currency, Reference).

#### Step 2: Select & Allocate Invoices
- The system automatically finds all unpaid and partially paid invoices from any customer sharing the same Tax ID.
- Displays a color-coded allocation table (Green = Selected, Blue = Unselected) with Invoice Number, Date, Customer, Tax ID, Branch, Residual Amount, and Allocated Amount.
- Auto-fill functionality respects the Tax ID grouping, allocating the payment using FIFO logic.

#### Step 3: Review & Confirm
- Review payment summary and the detailed split of allocations across the different customer entities sharing the Tax ID.
- "Confirm & Post" to process the transaction.

## Accounting Logic

1. **Create and post ONE payment**:
   - Partner = paying customer
   - Debit bank / credit AR (paying customer)

2. **For each allocation where invoice.partner_id != paying_partner_id**:
   - Create a CLEARING journal entry:
     - Debit AR (invoice customer)
     - Credit AR (paying customer)
     - Amount = allocated amount
     - Currency = invoice currency
     - Odoo handles FX differences automatically

3. **Reconcile**:
   - Invoice receivable line ↔ Clearing AR line (invoice customer)
   - Payment AR line ↔ Invoice AR line (paying customer, if any)

4. **DO NOT**:
   - Reconcile across different partners directly
   - Modify journal entries manually
   - Calculate FX manually
   - Use SQL

## Cancel & Reverse Support

### Cancel (period open):
- Unreconcile all related lines
- Cancel clearing journal entries
- Cancel payment safely

### Reverse (period closed):
- Use Odoo reverse entry mechanism
- Reverse both payment and clearing entries
- FX difference reverses automatically

## Data Models

### Wizard (Transient)
- `buz.clearing.payment.wizard`: Main wizard with payment header and allocation lines
- `buz.clearing.payment.line`: Allocation line for each invoice

### Persistent Models
- `buz.clearing.link`: Links payment, clearing entry, and invoice for complete traceability

## Installation

1. Copy the module to your Odoo addons directory.
2. Update the module list in Odoo.
3. Install the module `buz_inter_customer_clearing_payment`.

## Technical Notes

- Uses `account.partial.reconcile` for all reconciliations.
- All clearing entries store references to both the payment and the corresponding invoice.
- Extensively uses Tax ID (`vat`) filtering (`vat != False`) to ensure data integrity during allocations.
- No core Odoo modifications.
- Compatible with Odoo 17 Community and Enterprise editions.

## Security

- Access rights configured for accounting users and managers.
- Proper segregation of duties maintained.