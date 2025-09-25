# HR Expense Advance Clearing Module - Qwen.md

## Overview
The HR Expense Advance Clearing module enhances Odoo 17's Expense Management workflow by introducing a proper Advance/Petty Cash Clearing mechanism. It allows companies to manage Employee Advance Accounts (typically 141101) directly, supporting Thai accounting practices by avoiding the default behavior of forcing employee expenses into Accounts Payable (AP).

## Purpose
This module addresses the need for a proper advance management system that:
- Allows employees to request and clear advances seamlessly
- Posts journal entries directly against Advance Account (141101) instead of AP
- Supports VAT (Input Tax) and WHT (Withholding Tax) entries automatically
- Provides an Audit Trail: Link Expense → Journal Entry → Advance Box
- Tracks per-employee advance balance in real-time

## Key Components

### Models
1. **employee.advance.box** - Manages employee advance boxes with account tracking
2. **hr.expense** - Extended with advance clearing functionality
3. **hr.expense.sheet** - Expense sheets with advance clearing options
4. **hr.expense.config** - Configuration for tax and advance accounts

### Wizards
1. **advance.topup.wizard** - Handles advance top-up functionality
2. **advance.clear.wizard** - Manual clearing from advance
3. **advance.settlement.wizard** - Advance settlement functionality
4. **advance.refill.base.wizard** - Refill to base amount functionality

### Views
- Custom views for advance boxes, expense forms, and configuration

### Data Files
- Account configurations and system parameters for Thai accounting practices

## Architecture

### Accounting Flow
1. **Advance Top-up**: Dr 141101 Employee Advance / Cr 102101 Bank
2. **Expense Submission**: Dr 65xxx Expense, Dr 119xxx VAT Input / Cr 141101 Employee Advance, Cr 213xxx WHT Payable
3. **Settlement**: 
   - Expense < Advance: Dr 102101 Bank / Cr 141101 Employee Advance
   - Expense > Advance: Dr 141101 Employee Advance / Cr 102101 Bank

### Key Features
- **Advance Box per Employee** - Tracks advance balance and defines advance account
- **Wizard Integration** - Handles journal entry creation for top-up or refund
- **Expense Integration** - Checkbox to clear from advance, redirects credit from Payable → Advance Account
- **Tax Support** - Automatic posting of VAT and WHT entries

## File Structure
```
hr_expense_advance_clearing/
├── __init__.py
├── __manifest__.py
├── README.md
├── Qwen.md (this file)
├── prompt.md
├── data/
│   ├── account_data.xml
│   └── system_parameters.xml
├── models/
│   ├── __init__.py
│   ├── employee_advance_box.py
│   ├── hr_expense.py
│   └── hr_expense_config.py
├── security/
│   └── ir.model.access.csv
├── tests/
│   ├── __init__.py
│   └── test_advance_refill_base.py
├── views/
│   ├── advance_box_views.xml
│   ├── hr_expense_config_views.xml
│   └── hr_expense_views.xml
└── wizard/
    ├── __init__.py
    ├── advance_clear_wizard.py
    ├── advance_clear_wizard.xml
    ├── advance_refill_base_wizard.py
    ├── advance_refill_base_wizard.xml
    ├── advance_settlement_wizard.py
    ├── advance_settlement_wizard.xml
    ├── advance_topup_wizard.py
    └── advance_topup_wizard.xml
```

## Key Classes and Methods

### EmployeeAdvanceBox (models/employee_advance_box.py)
- Manages employee advance boxes with balance tracking
- Provides methods for balance computation
- Handles relationships with employees, accounts, and journals

### HrExpense and HrExpenseSheet (models/hr_expense.py)
- Extended with `clear_from_advance` boolean field
- Enhanced with advance clearing type selections
- Includes logic for advance amount handling

### HRExpenseConfig (models/hr_expense_config.py)
- Configuration model for tax and advance accounts
- Handles system parameters for account codes

### Wizard Classes
- AdvanceTopupWizard - Handles advance top-ups
- AdvanceClearWizard - Manual clearing functionality
- AdvanceSettlementWizard - Settlement processing
- AdvanceRefillBaseWizard - Refill to base amount

## Dependencies
- hr_expense: Core expense management functionality
- account: Accounting features
- l10n_th_account_tax: Thai tax localization
- mail: Mail/chatter functionality

## Configuration
The module uses system parameters for account code patterns:
- `hr_expense_advance_clearing.vat_input_account_code` (default: 119%)
- `hr_expense_advance_clearing.wht_payable_account_code` (default: 213%)
- `hr_expense_advance_clearing.advance_account_code` (default: 141101)

## Testing
Includes transaction tests in `tests/test_advance_refill_base.py` that validate:
- Base amount field functionality
- Refill wizard operations
- Overall advance management workflow

## Benefits
1. Matches real Thai accounting practices
2. Eliminates misuse of AP for advances
3. Simplifies reconciliation & audit
4. Provides clear visibility of advance balances per employee
5. Integrates seamlessly with existing Odoo expense workflows

## Development Notes
- The module follows Odoo 17 standards
- Includes proper security access controls
- Uses proper inheritance patterns for extending core functionality
- Implements proper journal entry creation and reconciliation
- Handles multi-currency scenarios appropriately

## Module Status
- Author: MOGEN IT
- Version: 17.0.1.0.0
- License: LGPL-3
- Installable: True
- Application: False