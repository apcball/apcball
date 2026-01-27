# Manufacturing Backdate Module (buz_mrp_backdate)

## Overview
This module allows backdating Manufacturing Orders in Odoo 17 with proper tracking and remarks.

## Features
- ✅ Add Backdate and Remark fields to Manufacturing Orders
- ✅ Wizard to set backdate before validation
- ✅ Automatically update Stock Moves dates
- ✅ Update Inventory Valuation (Stock Valuation Layers) dates
- ✅ Update Journal Entries dates (for automated valuation)
- ✅ Track backdate remarks across all related documents
- ✅ Proper access rights for MRP managers

## Installation
1. Copy the module to your Odoo addons directory
2. Update the app list: `Settings > Apps > Update Apps List`
3. Search for "Manufacturing Backdate"
4. Click Install

## Usage

### Method 1: Using Wizard (Recommended)
1. Open a Manufacturing Order
2. Click the "Set Backdate" button in the header
3. Enter the backdate and remark
4. Choose action:
   - **Set Backdate Only**: Just save the backdate info
   - **Set and Confirm**: Save and confirm the MO
   - **Set and Mark as Done**: Save, confirm, and mark as done
5. Click "Apply"

### Method 2: Direct Field Entry
1. Open a Manufacturing Order
2. Set the "Backdate" field manually
3. Enter a "Backdate Remark"
4. Confirm or mark as done normally

## Technical Details

### Models Extended
- `mrp.production`: Added backdate and backdate_remark fields
- `stock.move`: Added computed backdate_remark field
- `stock.valuation.layer`: Added computed backdate_remark field
- `account.move`: Added mrp_backdate_remark field

### Workflow
1. User sets backdate and remark on MO
2. On confirm: Stock moves are created with backdated date
3. On mark as done:
   - Stock moves dates are updated
   - Stock valuation layers dates are updated
   - Journal entries dates are updated
   - Remarks are propagated to all related documents

### Access Rights
- MRP User: Can view backdate wizard
- MRP Manager: Can set backdates and view all backdate fields

## Dependencies
- `mrp`: Manufacturing module
- `stock`: Inventory module
- `stock_account`: Inventory Accounting module

## Compatibility
- Odoo 17.0 Community/Enterprise

## Author
Your Company

## License
LGPL-3
