# Employee Advance Module Documentation

## Overview
The Employee Advance module provides a complete workflow for managing employee advances in Odoo 17. It maintains individual advance boxes per employee with refill-to-base functionality, handles expense clearing from advances, and creates draft vendor bills for accounting review.

## Features
- **Individual Advance Boxes**: Each employee has their own advance box with a dedicated account
- **Refill-to-Base Functionality**: Automatically calculates top-up amounts to reach a base target
- **Expense Management**: Submit expenses and clear from advance with proper workflow
- **Two Clearing Modes**: 
  - *Reimburse Employee*: Creates vendor bill to employee's private address
  - *Pay Vendor*: Allows selecting vendors per expense line and creates separate bills per vendor
- **Vendor Bill Creation**: Creates draft vendor bills after manager approval
- **Payment-Based Clearing**: Uses Register Payment wizard with default Advance Box Journal instead of manual journal entries
- **Settlement Functionality**: Close advance boxes with proper accounting entries when employee leaves or at year-end
- **Journal Entry Clearing**: Clear advances with proper accounting entries
- **VAT/WHT Reporting**: Support for tax reporting requirements
- **Manual Linking**: Ability to manually link vendor bills to advance boxes when needed

## Configuration

### System Parameters
- **Default Clearing Journal**: Journal used for clearing advances (Dr AP / Cr 141101)
- **Notify User**: User to notify when vendor bills are created from expenses
- **Notify Group**: Group to notify when vendor bills are created from expenses
- **Activity Type**: Activity type used for vendor bill notifications
- **Deadline Days**: Number of days for activity deadline

## Core Models

### Employee Advance Box (`employee.advance.box`)
Represents an individual advance box for each employee, including:

**Fields:**
- `name`: Auto-generated name based on employee name
- `employee_id`: Reference to the employee
- `account_id`: Account used for advance transactions (defaults to account code like 141101)
- `journal_id`: Journal for top-ups and refunds (bank/cash journals)
- `remember_base_amount`: Target base amount for refill functionality
- `balance`: Current balance computed from posted journal entries
- `currency_id`: Currency (defaults to company currency)
- `company_id`: Company reference

**Methods:**
- `action_refill_to_base`: Launches wizard to refill advance to base amount
- `_get_employee_partner`: Gets the partner associated with the employee for advance transactions

### Expense Sheet (`hr.expense.sheet`)
Extended to support advance clearing functionality:

**Additional Fields:**
- `clear_mode`: Selection field with options 'Reimburse Employee' or 'Pay Vendor'
- `use_advance`: Boolean to enable advance clearing
- `advance_box_id`: Reference to the advance box for clearing
- `bill_id`: Reference to the vendor bill created
- `payment_ids`: Related payments for the vendor bill

**Methods:**
- `action_approve_expense_sheets`: Creates vendor bill when approved with advance clearing
- `action_clear_advance`: Opens Register Payment wizard to clear the advance
- `_get_vendor_expense_lines`: Groups expense lines by vendor for Pay Vendor mode
- `_create_vendor_bills_for_vendors`: Creates separate vendor bills for each vendor
- `_create_vendor_bill_for_employee`: Creates vendor bill for employee reimbursement

### Expense Line (`hr.expense`)
Extended to support vendor selection:

**Additional Fields:**
- `vendor_id`: Partner field to select vendor when clear_mode is 'Pay Vendor'

**Methods:**
- `_onchange_clear_mode`: Clears vendor_id when switching to Reimburse Employee mode

## Workflows

### Expense to Advance Clearing Process (Reimburse Employee Mode)
1. Employee submits expense sheet with clear_mode set to "Reimburse Employee"
2. Employee selects their advance box from available options
3. Manager approves the expense sheet
4. System creates a draft vendor bill linked to the employee's private address
5. Accounting team processes the vendor bill
6. When clearing the advance, the Register Payment wizard opens with default Advance Box Journal
7. Payment is created which clears the advance balance

### Pay Vendor Mode Process
1. Employee submits expense sheet with clear_mode set to "Pay Vendor"
2. For each expense line, select the appropriate vendor (res.partner with supplier rank)
3. If no vendor is selected, the expense line goes to the employee bill group
4. On manager approval, system groups expense lines by (vendor_id or employee_partner, company, currency)
5. Creates separate draft vendor bills per vendor group
6. Each bill carries taxes (VAT, WHT), analytic, and expense accounts correctly
7. Accounting team processes the vendor bills
8. When clearing advances, use Register Payment wizard for each vendor bill

### Refill to Base Process
1. Navigate to an employee's advance box
2. Click the "Refill to Base" button
3. The wizard calculates the current balance and top-up amount needed
4. Confirm the refill to create a journal entry
5. The base amount is updated as the new target

### Manual Advance Linking
1. Open a vendor bill that needs to be linked to an advance
2. Click "Link to Advance" button
3. Select the appropriate advance box and optionally an expense sheet
4. The bill is now linked and can be cleared using advance balance

### Advance Settlement Process
1. Navigate to the Settlement menu under Expenses → Advance Management
2. View outstanding balances per employee advance box
3. Select an advance box with non-zero balance to settle
4. Open the "Settle Advance" wizard
5. The wizard automatically determines settlement type:
   - If balance > 0: Employee owes company (Dr 141101 / Cr Payable)
   - If balance < 0: Company owes employee (Dr Expense / Cr 141101)
6. Confirm the settlement to create the journal entry
7. The entry reconciles with advance transactions for full audit trail

## Views and User Interface

### Advance Box Views
- Tree view showing all advance boxes with balances and base amounts
- Form view with refill button and balance information
- Chatter for documenting transactions

### Expense Sheet Integration
- Additional fields for advance selection in expense forms
- Clear with Advance button when a bill is available
- Advance & Bill Information tab showing linked bill and payments

### Vendor Bill Integration
- Clear with Advance button on vendor bills
- Link to Advance wizard for manual linking
- Advance Info section showing associated advance box and expense sheet

### Expense Line Integration
- Vendor selection field available when clear_mode is 'Pay Vendor'
- Vendor field is hidden when clear_mode is 'Reimburse Employee'

### Settlement Views and Menus
- **Settlement Menu**: New menu item under Expenses → Advance Management
- **Settlement Tree View**: Shows all advance boxes with outstanding balances
- **Settlement Wizard**: Form view to handle advance box closure
- **Advance Box Form**: Added "Settle Advance" button when balance is non-zero

## Technical Implementation

### Account Move Extensions
The `account.move` model is extended with methods for clearing advances:
- `action_clear_advance_from_bill`: Main method to clear advance from vendor bill (now opens Register Payment wizard)
- `_open_register_payment_wizard`: Opens the payment wizard with default settings from advance box
- `_clear_advance_using_advance_box`: Creates clearing JE directly using advance box
- `action_post`: Override to handle advance clearing for payments

### Account Payment Extensions
The `account.payment` model is extended to track advance clearing:
- `is_advance_clearing`: Boolean field to identify advance clearing payments
- `reconciled_bill_ids`: One2many field to track reconciled bills

### Account Move Line Extensions
The `account.move.line` model is extended to update advance box balances:
- Triggers balance recompute when relevant lines are created/updated/deleted
- Monitors specific accounts and partners for advance box changes

### Settlement Wizard (`advance.settlement.wizard`)
Handles closing of advance boxes with proper accounting entries:

**Fields:**
- `advance_box_id`: Reference to the advance box to settle
- `settlement_type`: Computed field showing if employee owes company or vice versa
- `settlement_amount`: Computed field with the absolute balance amount
- `currency_id`: Currency for the settlement
- `journal_id`: Journal for the settlement entry
- `description`: Description for the settlement entry

**Methods:**
- `action_settle_advance`: Creates the settlement journal entry
- `_get_payable_account`: Gets the appropriate payable account
- `_get_expense_account`: Gets the appropriate expense account

### Mail Activity Types
- "Advance Bill Review" activity type for tracking vendor bill reviews

### Wizards
- `advance.refill.base.wizard`: Handles refill-to-base functionality
- `link.advance.wizard`: Manages manual linking of bills to advances

## Security
- Basic user can view advance boxes but only managers can edit
- Proper access controls for advance-related wizards
- Appropriate permissions for viewing and processing advance transactions

## Dependencies
- `hr_expense`: For expense management functionality
- `account`: For accounting and journal entries
- `mail`: For notifications and activities
- `hr_contract`: For employee address information

## Installation Notes
- The module is designed for Odoo 17.0
- Requires proper setup of advance accounts and journals
- Configure default clearing journal in settings
- Set up employee addresses for proper vendor bill creation

## Common Use Cases

### Standard Workflow
1. Create an advance box for each employee requiring advances
2. Employees submit expenses using the standard Odoo expense process
3. Enable "Clear from Advance" and select appropriate advance box
4. Manager approves the expense sheet
5. System creates draft vendor bill for accounting team
6. Accounting team reviews and posts the vendor bill
7. Bill can be paid and advance cleared automatically or manually

### Refill Operations
1. Regularly refill advance boxes to maintain base amounts
2. Use the refill functionality to maintain consistent advance balances
3. All transactions are properly recorded in the system

### Manual Processing
1. For special cases where automatic linking doesn't work
2. Use the "Link to Advance" functionality to manually connect bills
3. Process clearings with proper documentation

## Troubleshooting
- Ensure employee addresses are properly set for vendor bill creation
- Verify advance accounts are properly configured
- Check that default clearing journal is set in system parameters
- Verify that advance boxes have proper account and journal associations