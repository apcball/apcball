# Stock Valuation Location Module

## Overview
This module adds location information to stock valuation layers (SVL) in Odoo 17.

## Features
- Automatically computes and stores the internal location for each stock valuation layer
- Uses efficient batch processing to avoid N+1 query issues
- Location is determined from the related stock move:
  - Uses source location if it's internal
  - Otherwise uses destination location if it's internal
  - Remains empty for SVLs without stock moves (e.g., landed costs)

## Installation
1. Copy the module to your addons directory
2. Update the apps list: `Settings > Apps > Update Apps List`
3. Search for "buz Stock Valuation Location" and install

## Upgrade
After upgrade, the location_id field will be automatically computed for all existing stock valuation layers through Odoo's standard compute mechanism.

## Technical Details
- **Model**: `stock.valuation.layer`
- **New Field**: `location_id` (Many2one to `stock.location`)
- **Computation**: Automatic via `@api.depends('stock_move_id')`
- **Storage**: Stored and indexed for performance

## Version History
- **17.0.1.0.2**: Simplified version - removed SQL fast path functions
- **17.0.1.0.1**: Initial version with SQL optimization

## Author
Apcball - https://mogdev.work

## License
LGPL-3
