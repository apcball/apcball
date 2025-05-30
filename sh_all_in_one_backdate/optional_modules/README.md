# Optional Bank Statement Module

## Overview
This directory contains optional bank statement backdating functionality that may not be compatible with all Odoo installations.

## Files Included
- `account_bank_statement.py` - Bank statement model extensions
- `account_bank_statement_views.xml` - Bank statement view modifications

## Installation Instructions

### If you want to enable bank statement backdating:

1. **Check if bank statements are available in your Odoo installation:**
   - Go to Accounting > Bank and Cash > Bank Statements
   - If this menu exists, you can proceed with installation

2. **Copy the files to the main module:**
   ```bash
   cp optional_modules/account_bank_statement.py models/
   cp optional_modules/account_bank_statement_views.xml views/
   ```

3. **Update the models/__init__.py file:**
   Add this line:
   ```python
   from . import account_bank_statement
   ```

4. **Update the __manifest__.py file:**
   Add this line to the 'data' list:
   ```python
   'views/account_bank_statement_views.xml',
   ```

5. **Upgrade the module:**
   - Go to Apps > Installed Apps
   - Find "buz All In One Backdate Advanced"
   - Click "Upgrade"

## Compatibility Notes
- Bank statement functionality may not be available in all Odoo editions
- Some installations may have different view references
- This is why these files are kept separate from the main module

## Alternative Approach
If you encounter issues with bank statement views, you can:
1. Install the main module without bank statement support
2. Manually add bank statement backdating functionality later
3. Use the backdate wizard for bank statement lines if needed

## Support
If you need help with bank statement integration, please check:
- Your Odoo edition supports bank statements
- The account module is properly installed
- Bank statement views exist in your system