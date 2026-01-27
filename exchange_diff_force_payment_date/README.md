# Exchange Difference - Force Payment Date

## Overview
This module modifies the standard Odoo 17 behavior for exchange difference journal entries created during reconciliation.

## Problem
In standard Odoo 17, exchange difference journal entries (EXCH) use the reconciliation date (current date/today) when creating adjustment entries for foreign currency transactions.

## Solution
This module forces all exchange difference journal entries to use the **payment date** instead of the reconciliation date.

## Key Features
- ✅ Exchange difference entries use payment date, not reconciliation date
- ✅ Automatically detects payment moves in reconciliation
- ✅ Fallback mechanism: uses earliest date if no payment move is detected
- ✅ Works with both full and partial reconciliations
- ✅ Comprehensive logging for debugging

## Technical Details

### Models Extended
- `account.move.line` - Overrides `_prepare_exchange_difference_move_vals()`

### Logic Flow
1. **Detect Payment Move**: Identifies moves with:
   - Linked to `account.payment` via `payment_id` field
   - Lines from bank statements via `statement_line_id`
   - Journal entries in bank/cash journals (`journal_id.type` in ['bank', 'cash'])
   - Invoice + entry combinations (entry is treated as payment)

2. **Override Exchange Date**: Passes payment date to the exchange difference creation

3. **Fallback**: If no payment detected, uses standard Odoo behavior (max date of reconciled lines)

## Installation
1. Copy this module to your Odoo addons directory
2. Update apps list: `Settings > Apps > Update Apps List`
3. Search for "Exchange Difference - Force Payment Date"
4. Click Install

## Configuration
No configuration required. The module works automatically once installed.

## Usage
Simply perform reconciliation as normal. The module will automatically:
- Detect the payment move
- Set the exchange difference entry date to match the payment date

## Example Scenario
```
Invoice Date: 2024-01-15
Payment Date: 2024-02-10
Reconciliation Date: 2024-12-26

Standard Odoo: EXCH date = 2024-12-26 (reconciliation date)
With This Module: EXCH date = 2024-02-10 (payment date)
```

## Dependencies
- `account` (Odoo standard accounting module)

## Version
- Odoo Version: 17.0
- Module Version: 1.0.0

## License
LGPL-3

## Support
For issues or questions, please contact your Odoo administrator.
