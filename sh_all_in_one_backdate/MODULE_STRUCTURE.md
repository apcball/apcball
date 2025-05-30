# All In One Backdate Advanced - Module Structure

## Overview
This module provides comprehensive backdating functionality for Odoo 17, similar to the referenced module from the Odoo App Store.

## Module Structure

```
sh_all_in_one_backdate/
├── __init__.py                          # Module initialization
├── __manifest__.py                      # Module manifest
├── README.md                           # Documentation
├── MODULE_STRUCTURE.md                 # This file
│
├── data/
│   └── ir_cron.xml                     # Cron jobs for cleanup
│
├── models/
│   ├── __init__.py
│   ├── backdate_log.py                 # Audit trail model
│   ├── account_move.py                 # Invoice/Bill backdating
│   ├── account_payment.py              # Payment backdating
│   ├── sale_order.py                   # Sale order backdating
│   ├── purchase_order.py               # Purchase order backdating
│   ├── stock_picking.py                # Stock picking backdating
│   ├── account_bank_statement.py       # Bank statement backdating
│   └── res_config_settings.py          # Configuration settings
│
├── security/
│   ├── security.xml                    # Security groups and rules
│   └── ir.model.access.csv             # Access rights
│
├── static/
│   └── description/
│       ├── index.html                  # Module description page
│       └── icon_placeholder.txt        # Icon placement instructions
│
├── tests/
│   ├── __init__.py
│   └── test_backdate_functionality.py  # Unit tests
│
├── views/
│   ├── account_move_views.xml          # Invoice/Bill views
│   ├── account_payment_views.xml       # Payment views
│   ├── sale_order_views.xml            # Sale order views
│   ├── purchase_order_views.xml        # Purchase order views
│   ├── stock_picking_views.xml         # Stock picking views
│   ├── account_bank_statement_views.xml # Bank statement views
│   └── res_config_settings_views.xml   # Configuration views
│
└── wizard/
    ├── __init__.py
    ├── backdate_wizard.py              # Backdate wizard logic
    └── backdate_wizard_views.xml       # Wizard views
```

## Key Features Implemented

### 1. Document Support
- ✅ Customer Invoices (`account.move`)
- ✅ Vendor Bills (`account.move`)
- ✅ Customer/Vendor Payments (`account.payment`)
- ✅ Sale Orders (`sale.order`)
- ✅ Purchase Orders (`purchase.order`)
- ✅ Stock Pickings (`stock.picking`)
- ✅ Bank Statements (`account.bank.statement`)
- ✅ Bank Statement Lines (`account.bank.statement.line`)

### 2. Security & Permissions
- ✅ User Groups (Backdate User, Backdate Manager)
- ✅ Permission-based access control
- ✅ Date range restrictions for users
- ✅ Manager override capabilities
- ✅ Document state validation

### 3. Audit Trail
- ✅ Complete backdate logging (`backdate.log`)
- ✅ User activity tracking
- ✅ Reason tracking (optional/mandatory)
- ✅ Date change history
- ✅ Document reference linking

### 4. Configuration
- ✅ Maximum backdate days setting
- ✅ Reason requirement toggle
- ✅ Document type enable/disable
- ✅ Company-specific settings
- ✅ Automated log cleanup (cron)

### 5. User Interface
- ✅ Backdate buttons on document forms
- ✅ Backdate wizard for date selection
- ✅ Configuration settings page
- ✅ Backdate log views and menus
- ✅ Visual indicators for backdatable documents

### 6. Validation & Safety
- ✅ Future date prevention
- ✅ Fiscal year lock validation
- ✅ Maximum days restriction
- ✅ Document state validation
- ✅ Permission checks

### 7. Technical Features
- ✅ Proper date/datetime handling
- ✅ Transaction safety
- ✅ Error handling and user feedback
- ✅ Unit tests
- ✅ Comprehensive documentation

## Installation Steps

1. **Copy Module**: Place the `sh_all_in_one_backdate` folder in your Odoo addons directory
2. **Update Apps List**: Restart Odoo or update the apps list
3. **Install Module**: Go to Apps menu and install "All In One Backdate Advanced"
4. **Configure Settings**: Go to Settings > General Settings > Backdate section
5. **Assign Permissions**: Add users to appropriate backdate groups
6. **Add Icon**: Place a 128x128 PNG icon at `static/description/icon.png`

## Usage

1. **For Authorized Users**: Look for "Backdate" buttons on posted documents
2. **Select New Date**: Use the wizard to choose the backdate
3. **Provide Reason**: Enter justification if required
4. **Review Logs**: Check backdate logs for audit purposes

## Customization

The module is designed to be easily extensible:
- Add new document types by extending the pattern
- Modify validation rules in the `_validate_backdate` methods
- Customize the wizard interface
- Add additional audit fields to the log model
- Implement custom notification systems

## Compliance

- All operations are logged for audit trails
- Respects Odoo's fiscal year locks
- Maintains data integrity
- Provides proper user access controls
- Supports regulatory compliance requirements