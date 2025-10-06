
# buz_account_receipt (Odoo 17)

Generate a **grouped receipt** document (`account.receipt`) from multiple invoices directly from the invoice list view.
- Menu: Invoicing → Customers → Receipts (moved under Customers menu)
- New: Direct integration with invoice list view to create receipts from selected invoices
- New: Partner action to create receipts from customer contact form
- Removed: Receipt generation wizard (simplified workflow)
- Print QWeb: Receipt (PDF)

### Logic
- Creates `account.receipt` records from selected `account.move` records where `move_type in ('out_invoice','out_refund')`, `state='posted'`, and all belong to the same partner.
- For each invoice line in the receipt: 
  - Amount Total = invoice total
  - Residual = remaining due
  - Paid = Total - Residual (signed for refunds)
- Receipt Total = sum of line Paid.

### Creating Receipts from Invoice List
1. Go to Invoicing → Customers → Invoices
2. Select one or multiple invoices (all must belong to the same customer)
3. Click on "Action" → "Create Receipt"
4. A new receipt will be created with the selected invoices as lines
5. The receipt is automatically posted

### Creating Receipts from Customer Contact Form
1. Go to Invoicing → Customers → Customers
2. Open a customer's contact form
3. Click on the "Create Receipt" smart button
4. This will create a receipt for all posted invoices of that customer

### Validations
- All selected invoices must belong to the same partner
- Only posted invoices of type 'out_invoice' or 'out_refund' are allowed
- Only invoices with 'paid' or 'in_payment' status are allowed

### Batch Payment Registration

The module includes functionality to register batch payments directly from a receipt:

1. Open an existing receipt that has invoice lines
2. Click the "Register Batch Payment" button in the header
3. The standard payment registration wizard will open with all invoices pre-selected
4. Complete the payment registration as usual

This feature allows for efficient processing of payments for multiple invoices grouped in a receipt.
