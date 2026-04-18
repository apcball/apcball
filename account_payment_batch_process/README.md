# Account Payment Batch Processing

This module provides an advanced batch payment processing system for Odoo 17, extending the standard `account.payment.register` wizard. It allows users to process single batch payments (e.g., a single large cheque or wire transfer) and apply them across multiple invoices or vendor bills, potentially grouping them by partner.

## Key Features

1. **Multi-Invoice / Multi-Bill Payment**: Select multiple posted customer invoices or vendor bills and pay them together.
2. **Batch Amount Auto-Fill**: Enter a single "Batch Payment Total" (e.g., `cheque_amount`) and use the Auto-Fill feature to sequentially allocate the amount against the selected invoices.
3. **Partner Grouping**: The module intelligently groups payments by `partner_id`. Even if invoices from multiple partners are selected, it creates consolidated `account.payment` records per partner.
4. **Partial Payments & Write-offs**: For each invoice line in the batch, users can specify the exact amount to pay, and decide whether to leave the remaining balance open (`open`) or write it off (`reconcile`).
5. **Dynamic Payment Description**: Integrates with the `num2words` library to automatically generate the payment amount in words as part of the payment reference/description.

## Core Logic & Architecture

The module primarily overrides the `account.payment.register` wizard and introduces a new transient model `invoice.payment.line` to handle the line-by-line allocation.

### 1. Wizard Initialization (`default_get`)
When the wizard is launched from the action menu on selected `account.move` records:
- It verifies that all selected invoices are posted and unpaid/partially paid.
- It ensures you cannot mix customer invoices and vendor bills, or different currencies in a single batch.
- It populates the `invoice_payments` `One2many` list with an entry for each selected invoice, defaulting the payment amount to the invoice's residual balance.

### 2. Auto-Fill Logic (`auto_fill_payments`)
If the user inputs a `cheque_amount` (Batch Payment Total) that is less than the total of all selected invoices:
- The user can trigger `auto_fill_payments()`.
- The system sequentially applies the `cheque_amount` to the `invoice_payments` lines until the batch amount is exhausted.
- Any invoices further down the list will have their payment amount set to `0.0`.

### 3. Payment Execution (`make_payments`)
When the user confirms the batch payment:
1. **Data Grouping**: It iterates over the `invoice_payments` lines (where `amount > 0`) and groups them by `partner_id`.
2. **Payment Creation**: For each partner, it aggregates the total amount and creates a single `account.payment` record.
3. **Reconciliation**:
   - It iterates through the newly created payment lines and the lines of the targeted invoices.
   - It performs standard Odoo reconciliation using `.reconcile()` on matched accounts (receivable/payable).
   - If a payment difference handling is set to `reconcile` (write-off), it creates `account.partial.reconcile` records to write off the remainder against a specified write-off account.

## Technical Details

- **Models**:
  - `account.payment.register` (Inherited TransientModel)
  - `invoice.payment.line` (New TransientModel): Represents the allocation of funds to a specific invoice.
- **Dependencies**: `account`, `account_payment`
- **External Dependencies**: `num2words` (Python library for cheque amount text generation)

## Usage Instructions

1. Go to **Accounting > Customers > Invoices** or **Accounting > Vendors > Bills**.
2. Select multiple posted invoices/bills in the list view.
3. Click the **Action** (⚙️) menu and select **Register Payment**.
4. In the wizard:
   - To pay fully: Leave amounts as is and click **Create Payment**.
   - To pay a specific total sum: Enter the sum in **Batch Payment Total**, click the **Auto-Fill Pay Amount** button, and then **Create Payment**.
   - To handle write-offs: Adjust the line amount and change the Action from "Keep open" to "Mark invoice as fully paid". Select a Write-off account.

## KYLD Project Context
This module operates under the `buz` prefix designation for accounting workflows and uses the OCA base structure. It is designed to streamline bulk accounts payable (AP) and accounts receivable (AR) processes where a single physical transaction corresponds to multiple system invoices.
