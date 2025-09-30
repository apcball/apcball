# Qwen Code Assistant

This is a Qwen Code project. For more information about what Qwen Code can do for you, check out the documentation.

## Project Context

- **Date**: วันอังคารที่ 30 กันยายน 2568
- **OS**: Linux
- **Project Directory**: /opt/instance1/odoo17/custom-addons/buz_account_receipt

### Directory Structure

```
/opt/instance1/odoo17/custom-addons/buz_account_receipt/
├───__init__.py
├───__manifest__.py
├───QWEN.md
├───README.md
├───data/
│   └───sequence.xml
├───models/
│   ├───account_receipt.py
│   ├───__init__.py
│   └───__pycache__/
├───__pycache__/
│   └───__init__.cpython-312.pyc
├───reports/
│   └───account_receipt_report.xml
├───security/
│   └───ir.model.access.csv
├───views/
│   ├───account_receipt_views.xml
│   ├───account_invoice_receipt_action.xml
│   └───res_partner_receipt_action.xml
└───wizard/
```

## Changes Made to the buz_account_receipt Module

### 1. Removed Receipt Generation Wizard
- Removed the wizard interface that required date ranges and manual partner selection
- Removed all references to the wizard from XML views, manifests, and security files
- Cleaned up associated code in wizard files

### 2. Enhanced Receipt Creation from Invoice List
- Implemented a new server action that allows creating receipts directly from the invoice list view
- Users can now select multiple invoices and create a receipt with a single action
- Added proper validation to ensure only invoices from the same partner can be grouped in one receipt

### 3. Improved Menu Structure
- Moved the "Receipts" menu to be under the "Customers" menu in Odoo
- Positioned receipts directly after invoices for better user experience
- Simplified the menu structure so clicking "Receipts" directly shows the receipt documents

### 4. Partner Validation
- Added validation to ensure that receipts can only be created when all selected invoices belong to the same partner
- If invoices from different partners are selected, an error message is displayed

### 5. New Action Methods
- Added `action_create_receipt_from_invoices()` method to the AccountMove model
- This method handles both single and multiple invoice selection scenarios
- Proper filtering for posted invoices with appropriate payment statuses

## Technical Details

### Models Changed
- `account.move` (via inheritance in account_receipt.py) - Added receipt creation functionality
- `res.partner` (via inheritance in account_receipt.py) - Added receipt creation from partner

### Views Added
- Added server action for creating receipts from invoice list view
- Added server action for creating receipts from customer contact form

### Security Updates
- Removed security access record for the removed wizard model
- Maintained appropriate access rights for receipt models

## Usage

1. Go to Invoicing > Customers > Invoices
2. Select one or multiple invoices (all must belong to the same customer)
3. Click on "Action" > "Create Receipt"
4. A new receipt will be created with the selected invoices as lines
5. The receipt is automatically posted

Alternatively:
1. Go to Invoicing > Customers > Receipts
2. Click "Create" to manually create a receipt
3. Select the customer and add invoice lines manually

## Validations

- All selected invoices must belong to the same partner
- Only posted invoices of type 'out_invoice' or 'out_refund' are allowed
- Only invoices with 'paid' or 'in_payment' status are allowed