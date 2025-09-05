# Marketplace Settlement Module - Workflow Documentation

## Overview
This module provides comprehensive marketplace settlement functionality for Odoo 17, specifically designed for Thai marketplace integrations (Shopee, Lazada, etc.) with full AR/AP netting and fee allocation capabilities.

## Main Workflow Processes

### 1. Settlement Creation Process
**Entry Point:** `Accounting > Marketplace > Create Settlement`

#### Steps:
1. **Wizard Launch** → `marketplace.settlement.wizard`
   - Select marketplace partner, trade channel, journal
   - Auto-filter invoices based on trade channel
   - Configure deductions (fees, VAT, WHT)

2. **Preview Settlement** → `action_preview_settlement()`
   - Shows calculated totals and breakdown
   - Lists affected invoices
   - Allows final review before posting

3. **Create Settlement** → `action_create_settlement()`
   - Generates journal entry with proper debits/credits
   - Reconciles customer receivables
   - Creates settlement record with reference

**Process Flow:**
```
Wizard Form → Preview → Settlement Creation → Journal Entry Posted → Reconciliation
```

### 2. AR/AP Netting Process
**Entry Point:** Settlement form → "Setup AR/AP Netting" button

#### Steps:
1. **Netting Wizard** → `action_open_netting_wizard()`
   - Lists available vendor bills from same marketplace partner
   - Allows manual selection or auto-selection
   - Shows net amount calculation

2. **Confirm Netting** → `action_confirm_netting()`
   - Creates netting journal entry
   - Reconciles AR and AP accounts
   - Updates settlement with netting details

3. **Final Reconciliation** → Bank statement matching
   - Only net amount needs bank reconciliation
   - Simplified cash flow management

**Process Flow:**
```
Posted Settlement → Netting Wizard → Select Vendor Bills → Create Netting Entry → Net Reconciliation
```

### 3. Fee Allocation Process
**Entry Point:** Settlement form → "Generate Fee Allocations" or "Import CSV"

#### Steps:
1. **Generate Allocations** → `action_generate_fee_allocations()`
   - Creates proportional allocation based on invoice amounts
   - Distributes marketplace fees across invoices

2. **Import CSV Allocations** → `action_import_fee_allocations_csv()`
   - Allows exact fee allocation from marketplace reports
   - Validates and imports allocation data

3. **View/Edit Allocations** → `action_view_fee_allocations()`
   - Review and adjust individual allocations
   - Generate allocation reports

**Process Flow:**
```
Posted Settlement → Generate/Import Allocations → Review Allocations → Generate Reports
```

### 4. Vendor Bill Management Process
**Entry Point:** `Accounting > Marketplace > Vendor Bills`

#### Steps:
1. **Document Import** → Manual or CSV import
   - TR (Tax Invoice) for Shopee
   - RC (Receipt) for SPX
   - Automatic profile detection

2. **Bill Creation** → `action_create_vendor_bill()`
   - Generates Odoo vendor bill
   - Applies correct taxes and accounts
   - Links to marketplace settlement

**Process Flow:**
```
Document Import → Validation → Vendor Bill Creation → Available for Netting
```

### 5. Thai Localization (WHT) Process
**Entry Point:** Settlement form → WHT fields

#### Steps:
1. **WHT Configuration** → Enable Thai WHT in settlement
   - Configure income type and tax form
   - Set WHT percentage and accounts

2. **Certificate Generation** → `action_create_wht_certificate()`
   - Creates WHT certificate record
   - Links to settlement for compliance

**Process Flow:**
```
Settlement with WHT → Configure WHT Details → Generate Certificate → Compliance Reporting
```

## Process Connections & Dependencies

### Settlement → Netting
- Settlement must be **posted** before netting
- Netting wizard filters vendor bills by marketplace partner
- Net amount calculation considers both receivables and payables

### Settlement → Fee Allocation
- Allocations can only be created for **posted** settlements
- Supports both proportional and exact allocation methods
- Allocation data used for reporting and analytics

### Vendor Bills → Netting
- Bills must be **posted** and have residual amounts
- Automatic filtering by marketplace partner
- Integration with settlement netting process

### Profile → All Processes
- Profiles provide default configurations
- Auto-populate accounts and settings
- Channel-specific behavior configuration

## Key Integration Points

1. **Sales Order Integration**
   - Trade channel copied to invoices
   - Automatic filtering in settlement wizard

2. **Account Move Extensions**
   - Trade channel field on invoices
   - Settlement reference tracking
   - Reconciliation status

3. **Partner Extensions**
   - Marketplace partner identification
   - Default account configurations
   - Thai localization fields

## Error Handling & Validation

### Pre-Creation Validations
- Invoice state verification (must be posted)
- Account configurations (expense, VAT, WHT accounts)
- Currency consistency checks
- Partner receivable account validation

### Process Validations
- Settlement state checks before netting
- Vendor bill availability for netting
- Fee allocation amount consistency
- WHT configuration completeness

### Security Controls
- User group permissions (account.group_account_user)
- State-based button visibility
- Modification restrictions on posted records

## Common Usage Scenarios

### Scenario 1: Simple Settlement (No Netting)
1. Create settlement wizard with marketplace invoices
2. Add marketplace fees and taxes
3. Preview and create settlement
4. Reconcile net amount with bank statement

### Scenario 2: Settlement with AR/AP Netting
1. Create basic settlement (as above)
2. Open netting wizard and select vendor bills
3. Create netting entry
4. Reconcile smaller net amount with bank

### Scenario 3: Detailed Fee Allocation
1. Create settlement and generate basic allocations
2. Import detailed CSV from marketplace
3. Review and adjust allocations
4. Generate allocation reports for analysis

## Troubleshooting Guide

### Common Issues:
1. **"Settlement account is receivable"** → Use bank/liquidity account
2. **"No vendor bills for netting"** → Check partner matching and bill states
3. **"Fee allocation mismatch"** → Verify CSV format and amounts
4. **"WHT certificate error"** → Check Thai localization configuration

### Performance Considerations:
- Large invoice sets may need batching
- Fee allocation calculations cached for performance
- Netting limited to reasonable bill quantities

This comprehensive workflow ensures all marketplace settlement processes are properly connected and function seamlessly together.
