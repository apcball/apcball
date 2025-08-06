# HR Expense Advance Clearing - Odoo 17 Implementation

## Overview
The `hr_expense_advance_clearing` module has been successfully updated for Odoo 17 compatibility. This module allows employees to request advances and then clear them against actual expenses.

## Changes Made for Odoo 17

### 1. Version Update
- Updated version from `16.0.1.0.3` to `17.0.1.0.0` in `__manifest__.py`

### 2. Field Updates
- Changed `reconciled` field references to `is_reconciled` for Odoo 17 compatibility
- Updated `matching_number` field reference to `is_reconciled` in account move reconciliation logic

### 3. Product Configuration
- Fixed the advance product to set `can_be_expensed = True` to allow it to be used in expenses

### 4. Core Files Structure
```
hr_expense_advance_clearing/
├── __manifest__.py          # Module manifest with v17.0.1.0.0
├── __init__.py             # Module initialization
├── models/
│   ├── __init__.py
│   ├── hr_expense.py       # Expense model extensions
│   ├── hr_expense_sheet.py # Expense sheet model extensions
│   ├── hr_employee_base.py # Employee model extensions
│   ├── account_move.py     # Account move model extensions
│   └── account_payment.py  # Payment model extensions
├── wizard/
│   ├── __init__.py
│   └── account_payment_register.py # Payment registration wizard
├── views/
│   ├── hr_expense_views.xml
│   ├── hr_employee_views.xml
│   ├── hr_employee_public_views.xml
│   └── account_payment_view.xml
├── data/
│   └── advance_product.xml  # Employee advance product definition
└── tests/
    └── test_hr_expense_advance_clearing.py # Automated tests
```

## Key Features

### 1. Employee Advance Management
- Create advance requests for employees
- Validate advance product and account settings
- Track advance amounts and remaining balances

### 2. Advance Clearing
- Clear advances against actual expenses
- Handle partial clearings (less than advance amount)
- Handle over-clearings (more than advance amount)
- Automatic reconciliation of advance and clearing entries

### 3. Financial Integration
- Proper journal entry creation
- Account reconciliation
- Payment state management
- Integration with standard Odoo accounting flows

## Installation Instructions

### 1. Prerequisites
- Odoo 17 instance running
- `hr_expense` module installed and configured

### 2. Installation Steps

```bash
# 1. Copy the module to Odoo addons directory
cp -r hr_expense_advance_clearing /path/to/odoo17/addons/

# 2. Update module list
# Go to Apps > Update Apps List

# 3. Install the module
# Go to Apps > Search for "buz Employee Advance and Clearing" > Install
```

### 3. Configuration

1. **Configure Advance Product Account**:
   - Go to Accounting > Configuration > Chart of Accounts
   - Create or configure an account for employee advances (typically a current asset account)
   - Set this account as the expense account for the "Employee Advance" product

2. **Set Account as Reconcilable**:
   - Ensure the advance account has "Allow Reconciliation" enabled

3. **Configure Employee Advance Product**:
   - Go to Inventory > Products > Products
   - Find "Employee Advance" product
   - Set the expense account to your configured advance account

## Usage Workflow

### Creating an Advance
1. Go to Expenses > My Reports > Advances
2. Create new expense sheet
3. Add expense line with "Employee Advance" product
4. Set amount and submit for approval
5. Once approved, create journal entry
6. Register payment to complete advance

### Clearing an Advance
1. Go to Expenses > My Reports > Expenses
2. Create new expense sheet for actual expenses
3. In the expense sheet, select the advance to clear under "Clear Advance"
4. Add actual expense lines
5. Submit and approve
6. System automatically reconciles advance with actual expenses

## Testing

Run the automated tests to verify functionality:

```bash
# Run specific module tests
odoo-bin -d your_database -i hr_expense_advance_clearing --test-enable --stop-after-init
```

## Key Fields and Models

### HrExpense Model Extensions
- `advance`: Boolean field to mark advance expenses
- `clearing_product_id`: Product to use when clearing advance
- `av_line_id`: Reference to advance expense line

### HrExpenseSheet Model Extensions
- `advance`: Boolean field to mark advance sheets
- `advance_sheet_id`: Reference to advance sheet being cleared
- `clearing_sheet_ids`: One2many to clearing sheets
- `clearing_residual`: Amount remaining to be cleared
- `advance_sheet_residual`: Remaining amount from selected advance

## Validation Rules

1. **Advance Validation**:
   - Must use designated advance product
   - No taxes allowed on advances
   - Must be paid by employee (own_account)
   - Advance account must be properly configured

2. **Clearing Validation**:
   - Cannot clear more than available advance amount
   - Proper reconciliation of accounting entries
   - State management based on clearing amounts

## Troubleshooting

### Common Issues

1. **"Employee advance product has no payable account"**
   - Solution: Configure the expense account for the Employee Advance product

2. **"Employee advance, selected product is not valid"**
   - Solution: Ensure you're using the correct Employee Advance product for advances

3. **Reconciliation Issues**
   - Solution: Check that the advance account is marked as reconcilable

## Support and Maintenance

This module is based on the OCA (Odoo Community Association) version and has been adapted for Odoo 17. For issues or enhancements:

1. Check the automated tests for expected behavior
2. Review the validation rules in the models
3. Ensure proper account configuration

## License
AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
