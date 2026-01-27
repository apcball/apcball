# Inter-Customer Clearing Payment Module

## Overview

This module provides a user-friendly wizard to receive a customer payment and allocate that payment to invoices of multiple customers using inter-customer clearing logic, while remaining 100% accounting-correct and audit-safe.

## Business Scenario

- Customers are separated by branch (each branch = different customer record)
- One branch/customer sends a lump-sum payment
- That payment must be used to settle invoices of other customers/branches
- Master data CANNOT be changed
- AR Aging and audit trail must remain correct

## Features

- **User-Friendly 3-Step Wizard**: Intuitive interface for processing clearing payments
- **Partial Payment Support**: Allocate partial amounts to invoices
- **Multi-Currency Support**: Automatic FX handling by Odoo
- **Cancel & Reverse Functionality**: Full support for cancellation and reversal
- **Accounting-Correct**: All entries follow proper accounting principles
- **Audit-Safe**: Complete audit trail maintained

## User Experience Flow

### Menu Location
Accounting → Customers → Receive Clearing Payment

### Wizard Steps

#### Step 1: Payment Header
- Paying Customer (required)
- Payment Journal (bank/cash, required)
- Payment Date (required)
- Currency (related to journal)
- Payment Amount (required)
- Reference (optional)

#### Step 2: Allocate Invoices
- Selectable, editable table with:
  - Select (Boolean)
  - Customer
  - Branch (analytic account)
  - Invoice Number
  - Invoice Date
  - Residual Amount
  - Allocation Amount (editable)

- Helper buttons:
  - Auto-fill FIFO
  - Clear allocation
  - Filter by customer/branch

- Summary bar showing:
  - Amount Received
  - Total Allocated
  - Remaining Amount

#### Step 3: Review & Confirm
- Payment summary
- Allocation summary by customer & invoice
- Remaining advance amount
- Read-only accounting preview
- "Confirm & Post" button

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
- `buz.clearing.link`: Links payment, clearing entry, and invoice for tracking

## Installation

1. Copy the module to your Odoo addons directory
2. Update the module list in Odoo
3. Install the module "Inter-Customer Clearing Payment"

## Usage

1. Navigate to Accounting → Customers → Receive Clearing Payment
2. Follow the 3-step wizard:
   - Enter payment details
   - Allocate to invoices of multiple customers
   - Review and confirm
3. The system will automatically create the payment, clearing entries, and reconciliations

## Technical Notes

- Uses `account.partial.reconcile` for all reconciliations
- All clearing entries store references to payment and invoice
- No core Odoo modifications
- Compatible with Odoo 17 Community and Enterprise editions
- Follows Odoo ORM and accounting best practices

## Security

- Access rights configured for accounting users and managers
- Proper segregation of duties maintained

## Support

For support or questions regarding this module, please contact your system administrator.