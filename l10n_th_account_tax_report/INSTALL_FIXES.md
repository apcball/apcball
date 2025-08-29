# l10n_th_account_tax_report - Installation Guide

## Fixes Applied

This module has been optimized to resolve common installation issues:

### 1. Dependency Management
- Added `account` as an explicit dependency
- Reordered dependencies for better loading sequence
- Added error handling for missing imports

### 2. Performance Optimizations
- Reordered data loading sequence to prevent hangs
- Added timeout protection during installation
- Improved error handling in Python imports

### 3. Security Access Rules
- Fixed duplicate names in ir.model.access.csv
- Cleaned up security rule naming conventions

### 4. Installation Improvements
- Added post-installation hook for verification
- Added external dependency declarations
- Created dependency checking script

## Installation Instructions

### Method 1: Using the Installation Script (Recommended)
```bash
cd /opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report
./install_module.sh
```

### Method 2: Manual Installation
```bash
# Check dependencies first
python3 test_dependencies.py

# Install via Odoo command line
cd /opt/instance1/odoo17
python3 odoo-bin -d YOUR_DATABASE --stop-after-init -i l10n_th_account_tax_report
```

### Method 3: Via Odoo Web Interface
1. Go to Apps menu in Odoo
2. Remove "Apps" filter
3. Search for "Thai Localization - VAT"
4. Click Install

## Troubleshooting

### Installation Hangs
- **Cause**: Large number of XML files being loaded
- **Solution**: Use the installation script with timeout protection
- **Alternative**: Install dependencies individually first

### Missing Dependencies Error
- **Cause**: Required Thai localization modules not installed
- **Solution**: Install in this order:
  1. `l10n_th_base_utils`
  2. `l10n_th_partner`
  3. `l10n_th_account_tax`
  4. `l10n_th_account_tax_report`

### Database Permission Errors
- **Cause**: Insufficient database privileges
- **Solution**: Ensure the Odoo user has proper database permissions

### Python Import Errors
- **Cause**: Missing xlsxwriter package
- **Solution**: Install with `pip install xlsxwriter`

## Changes Made

1. **__manifest__.py**:
   - Added `account` dependency
   - Reordered data loading sequence
   - Added external Python dependencies
   - Added post_init_hook

2. **__init__.py**:
   - Added try/catch blocks for safe imports
   - Added post_init_hook function

3. **security/ir.model.access.csv**:
   - Fixed duplicate access rule names
   - Improved naming conventions

4. **Added Files**:
   - `test_dependencies.py`: Dependency checker
   - `install_module.sh`: Automated installation script
   - `INSTALL_FIXES.md`: This documentation

## Verification

After installation, verify the module is working by:
1. Going to Accounting > Reports
2. Looking for "Thai Tax Reports" menu items
3. Creating a tax report wizard

## Support

If you still experience issues:
1. Check the Odoo logs for specific error messages
2. Verify all dependencies are properly installed
3. Ensure the database user has sufficient privileges
4. Try installing in a test database first
