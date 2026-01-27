# Employee Advance Module - Qwen.md

## Module Overview
- **Name**: Employee Advance
- **Version**: 17.0.1.0.0
- **Category**: Human Resources
- **Summary**: Employee Advance Management with Advance Box and Bill Clearing
- **Dependencies**: hr_expense, account, mail, hr_contract, l10n_th_account_tax, l10n_th_account_wht_cert_form

## Description
This module implements a complete workflow for employee advances:
- Maintain Advance Box per employee with Refill-to-Base functionality
- Submit expenses and clear from advance
- Create draft vendor bills after manager approval
- Clear advances with payment wizard
- Support for VAT/WHT reporting
- Clearing mode: Reimburse Employee
- Settlement functionality for closing advance boxes
- Integration with Thai withholding tax (WHT) certificate functionality
- NEW: Separate bills for same employee with different dates
- NEW: Group by partner and date for proper accounting separation
- NEW: Use expense sheet date as accounting date in bills

## New Features: Date-Based Expense Grouping
This module now includes enhanced functionality for separate bills based on expense line dates:
- **NEW**: Same employee with expenses from different dates (in same or different sheets) will have separate bills
- **NEW**: Expenses are grouped by partner, company, currency, AND expense line date
- **NEW**: Accounting date in bills uses expense line date (not expense sheet date)
- **NEW**: Separate vendor bills created for same employee/partner with different expense dates
- **NEW**: Grouping key: (partner_id, company_id, currency_id, expense_line_date)
- **NEW**: Date-based grouping now applied to all expense types regardless of vendor/employee classification

## New Features: WHT Certificate Integration
This module now includes integration with the Thai Withholding Tax Certificate functionality:

### 1. WHT Certificate Creation
- When creating vendor bills from expense sheets, WHT taxes from expense lines are properly transferred to vendor bill lines
- WHT certificates are automatically created when clearing advances if the vendor bill contains WHT lines
- Integration with existing Thai tax modules ensures compliance with local requirements

### 2. UI Elements for WHT Certificates
- **Expense Sheet Form**: New \"Print WHT Certificates\" button appears when associated vendor bill has WHT certificates
- **WHT Certificates Section**: Displays associated WHT certificates on expense sheet for easy access
- **Account Move Form**: Enhanced with WHT certificate access and display

### 3. Model Extensions
- Extended `HrExpenseSheet` model with WHT certificate support
- Extended `AccountMove` model to handle WHT certificate creation during advance clearing
- Added `has_wht_certs` computed field to track if associated bill has WHT certificates

## Technical Architecture

### Models
1. **advance_box.py**: Employee advance box management
2. **expense_sheet.py**: Expense sheet extensions with advance functionality
3. **account_move.py**: Journal entry extensions for advance clearing
4. **wht_integration.py**: New module with WHT certificate functionality

### Views
1. **expense_sheet_views.xml**: Enhanced with WHT certificate UI elements
2. **account_move_views.xml**: Enhanced with WHT certificate UI elements
3. Other view files as per original module

### Data Files
1. **mail_activity_types.xml**: Activity types for advance management
2. Various data files from the original module

### Test Files
1. **test_wht_integration.py**: Tests for WHT certificate integration functionality
2. **test_wht_fix_verification.py**: Verification tests for WHT-related fixes
3. **test_updated_integration.py**: Updated integration tests for the module

## Dependencies
This module extends functionality from:
- `hr_expense`: Core expense management
- `account`: Core accounting functionality 
- `l10n_th_account_tax`: Thai tax localization (NEW)
- `l10n_th_account_wht_cert_form`: Thai WHT certificate form (NEW)

## Key Methods and Fields Added
1. `_create_vendor_bill_and_activity()`: Enhanced with WHT support
2. `_clear_advance_using_advance_box()`: Creates WHT certificates when appropriate
3. `create_wht_cert_from_advance_clearing()`: Creates WHT certificates for advance transactions
4. `has_wht_certs` (field): Computed field to track if associated vendor bill has WHT certificates
5. `_compute_has_wht_certs()`: Computes if associated vendor bill has WHT certificates
6. `_create_bills_by_vendor_grouping()`: Enhanced to include date in grouping key (partner, company, currency, date)
7. `_create_single_bill_for_vendor_group_date()`: New method to handle date-specific bill creation

## Integration Points
1. **WHT Tax Transfer**: When creating vendor bills from expense sheets, WHT taxes are properly transferred
2. **Certificate Creation**: During advance clearing, system checks for WHT on original bill and creates certificates if needed
3. **UI Integration**: Provides easy access to print WHT certificates from expense sheets and account moves
4. **Data Relationship**: Links expense sheets to vendor bills and their associated WHT certificates using computed field
5. **View Integration**: Fixed to use computed field instead of direct nested relationship

## Configuration
- The module requires proper configuration of Thai tax modules for WHT functionality
- Dependencies are managed in the manifest file
- Integration works seamlessly with existing advance management workflow

## User Workflow
1. Employee submits expense sheet with potential WHT
2. Manager approves expense sheet, creating vendor bill with WHT if applicable
3. During advance clearing, system automatically creates WHT certificates if required
4. Users can access and print WHT certificates from the expense sheet interface
5. WHT certificates are linked to both vendor bills and related expense sheets
6. The UI elements (buttons and sections) are visible only when WHT certificates exist

## Important Notes
- This module now requires the Thai tax localization modules to be installed
- WHT certificates follow Thai standard format as implemented in l10n_th_account_wht_cert_form
- All existing functionality from the original employee advance module is preserved
- The integration ensures compliance with Thai tax reporting requirements
- Fixed view issues by implementing a computed field approach for better performance and reliability
- The implementation maintains backward compatibility while adding new WHT functionality
- Test files have been added to ensure proper WHT integration and functionality

## Testing
The module includes comprehensive test coverage:
- Unit tests for WHT certificate creation and integration
- Integration tests for advance clearing with WHT
- Verification tests to ensure WHT-related fixes work properly
- Updated tests to cover new functionality and ensure no regressions