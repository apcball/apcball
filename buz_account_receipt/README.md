
# buz_account_receipt (Odoo 17)

Generate a **grouped receipt** document (`account.receipt`) from multiple invoices by partner & date range.
- Menu: Accounting → Customers → Receipts
- New: Direct integration with invoice list view to create receipts from selected invoices
- New: Batch Payment Registration - register payments directly from receipts
- Print QWeb: Receipt (PDF)

### Logic
- Picks `account.move` where `move_type in ('out_invoice','out_refund')`, `state='posted'`, matching partner & `invoice_date` in range.
- Includes invoices with `payment_state` in `['paid','in_payment']` (configurable via wizard checkbox).
- For each invoice line in the receipt: 
  - Amount Total = invoice total
  - Residual = remaining due
  - Paid = Total - Residual (signed for refunds)
- Receipt Total = sum of line Paid.

> Note: If you want to filter by **actual payment date**, extend the wizard to traverse reconciliations on move lines.

### Batch Payment Registration

The module now includes functionality to register batch payments directly from a receipt:

1. Open an existing receipt that has invoice lines
2. Click the "Register Batch Payment" button in the header
3. The standard payment registration wizard will open with all invoices pre-selected
4. Complete the payment registration as usual

This feature allows for efficient processing of payments for multiple invoices grouped in a receipt.
