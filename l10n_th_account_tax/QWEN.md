# Thai Accounting Tax Module (l10n_th_account_tax)

## Overview
This is an Odoo module for handling Thai accounting tax requirements, including withholding tax and personal income tax (PIT) calculations. The module extends core Odoo accounting functionality to comply with Thai tax regulations.

## Key Features
- Withholding tax management
- Personal Income Tax (PIT) rates and calculations
- Tax invoices and certificates
- Integration with account moves and reconciliations

## File Structure
- `models/` - Core model extensions for tax handling
- `data/` - Reference data for tax rates and types
- `views/` - UI views for tax management
- `wizard/` - Interactive wizards for tax processes
- `security/` - Access control and security rules
- `i18n/` - Translation files

## Models
- `account_move.py` - Extends account moves with tax functionality
- `account_move_tax_invoice.py` - Handles tax invoice generation
- `account_partial_reconcile.py` - Manages partial reconciliations with tax implications

## Data Files
- `pit_rate_data.xml` - Personal Income Tax rates
- `withholding_tax_cert_data.xml` - Withholding tax certificate configurations
- `withholding_tax_type_income_data.xml` - Withholding tax types based on income

## Usage Notes
This module is designed for Thai businesses that need to comply with local tax regulations. It extends Odoo's standard accounting functionality with Thai-specific tax requirements.

## Configuration
The module needs to be properly configured with correct tax rates and types based on current Thai tax laws. Make sure to update the data files as tax regulations change.

## Dependencies
This module likely depends on core Odoo accounting modules and potentially other l10n_th localization modules.