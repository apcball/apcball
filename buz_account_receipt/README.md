
# buz_account_receipt (Odoo 17)

Generate a **grouped receipt** document (`account.receipt`) from multiple invoices by partner & date range.
- Menu: Accounting → Customers → Receipts
- Wizard: Generate Receipt (choose Partner + Date range)
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
