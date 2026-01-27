# WHT Clear Advance Feature Documentation

## Overview
The "Clear Advance (with WHT)" feature allows users to clear employee advances while applying Withholding Tax (WHT) calculations. This feature creates proper accounting entries and supports Thai WHT certificate generation.

## Workflow

### 1. Prerequisites
- Employee Advance module must be installed
- Thai localization modules must be installed:
  - `l10n_th_account_tax`
  - `l10n_th_account_wht_cert_form`
- Employee must have an Advance Box configured
- Expense Sheet must be approved and not yet billed

### 2. Access the Feature
1. Go to **Human Resources** → **Expenses** → **Expense Reports**
2. Open an approved expense sheet that uses advance
3. Click the **"Clear Advance (WHT)"** button

### 3. Fill the WHT Wizard
The wizard will open with the following fields:

#### Required Fields:
- **Partner**: Select the vendor or employee for whom the payable will be created
- **WHT Tax**: Select the withholding tax from the dropdown (filtered to show only WHT taxes)
- **Base Amount**: Enter the base amount for WHT calculation
- **Clear Amount**: Enter the total amount to clear from the advance
- **Journal**: Select the general/miscellaneous journal for the entry

#### Auto-calculated Fields:
- **WHT Amount**: Automatically calculated as Base Amount × Tax Rate

#### Optional Fields:
- **Date**: Journal entry date (defaults to today)
- **Reference**: Optional reference for the journal entry

### 4. Journal Entry Creation
When you click **"Create & Post Journal Entry"**, the system creates:

```
Dr. Partner Payable Account        = Clear Amount
   Cr. Employee Advance Account    = Clear Amount - WHT Amount  
   Cr. WHT Payable Account         = WHT Amount
```

### 5. WHT Certificate Creation
After the journal entry is created:

1. The system opens the journal entry form
2. Use the **"Create WHT Certificate"** smart button to generate WHT certificates
3. The WHT certificate wizard will be pre-filled with the journal entry details
4. Complete and save the WHT certificate

## Features

### Smart Buttons
- **Create WHT Certificate**: Available on journal entries created by WHT advance clearing
- **WHT Certificates**: Shows count and opens related certificates

### Validation
- Clear amount must be greater than zero
- WHT amount cannot be negative  
- WHT amount must be less than clear amount
- Base amount must be greater than zero
- Advance box must have sufficient balance

### Security
- Access rights are configured for HR users and managers
- All operations respect Odoo's standard security model

## Technical Details

### Models Extended
- `hr.expense.sheet`: Added WHT clearing methods and button visibility
- `account.move`: Added WHT certificate creation and smart buttons
- `wht.clear.advance.wizard`: New wizard model for WHT clearing

### New Fields Added
- **account.move**: `wht_tax_id`, `wht_base_amount`, `wht_amount`, `is_advance_clearing`, `wht_cert_count`

### Configuration
- WHT taxes are filtered using the domain: `l10n_th_is_withholding = True` or `tax_scope = 'withholding'`
- General journals are used for miscellaneous entries
- Partner payable accounts are used from partner configuration

## Troubleshooting

### Common Issues
1. **"No WHT taxes available"**: Check that Thai tax modules are installed and WHT taxes are configured
2. **"Insufficient advance balance"**: Ensure the advance box has enough balance
3. **"WHT Certificate module not found"**: Install `l10n_th_account_wht_cert_form` module

### Support
- Check the advance box configuration
- Verify Thai localization modules are installed
- Ensure proper account configuration for partners and WHT taxes