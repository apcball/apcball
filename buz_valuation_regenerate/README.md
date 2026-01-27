# Re-Generate Valuation & Entries (buz_valuation_regenerate)

## Overview

This module provides functionality to delete and re-create Stock Valuation Layers (SVL) 
and related Journal Entries for selected products, date ranges, and companies. 
It includes a wizard interface with dry-run capabilities, backup functionality, 
and support for Landed Costs scenarios.

## Features

- **Regeneration Wizard**: A user-friendly interface to select scope and options for regeneration
- **Multiple Scoping Options**: By product, product category, or domain filter
- **Costing Method Support**: Handles FIFO and AVCO costing methods
- **Landed Cost Integration**: Properly handles products affected by landed costs
- **Dry Run Mode**: Calculate and preview changes without modifying data
- **Backup and Rollback**: Automatic backup of original data with rollback capabilities
- **Multi-company Support**: Works safely in multi-company environments
- **Lock Date Validation**: Respects accounting period locks and fiscal year locks
- **CSV Export**: Generate CSV reports showing before/after differences

## Usage

### From Product Form
1. Go to Inventory > Products
2. Open any product form
3. Click the "Re-Generate Valuation Layer" button in the action menu
4. Configure the regeneration options in the wizard
5. Click "Compute Plan (Dry-run)" to preview changes
6. Click "Apply Regeneration" to execute the regeneration

### From Menu
1. Go to Inventory > Configuration > Valuation Tools > Valuation Regenerator
2. Follow the same steps as above

### Regeneration Options

- **Company**: Select the company to work with
- **Scope**: Choose to regenerate by product, category, or domain
- **Date Range**: Optional date range to limit the regeneration
- **Options**:
  - Rebuild Valuation Layers: Delete and recreate SVLs
  - Rebuild Journal Entries: Delete and recreate related journal entries
  - Include Landed Cost Layers: Include landed cost adjustments in regeneration
  - Recompute Cost Method: Choose auto, FIFO, or AVCO
  - Dry Run: Calculate without modifying data
  - Force rebuild if locked: Override lock dates (use with caution)
  - Post New Journal Entries: Automatically post new journal entries

## Important Notes

⚠️ **Warning**: This is a powerful module that can significantly alter your inventory valuation data. 
Always test on a staging environment before using in production.

- Always perform a dry run first to preview changes
- Ensure no dependent transactions have been created since the period you're regenerating
- Backups are automatically created before regeneration
- The rollback feature should be used with caution as it cannot always fully restore all dependencies

## References

This module implements functionality similar to the concept described in Odoo's official documentation about 
automatic inventory valuation, and is designed to work alongside tools like the Stock Valuation Layer Usage 
module from OCA for better traceability of cost layer changes.

- [Odoo 17 Official Documentation on Inventory Valuation](https://www.odoo.com/documentation/17.0/applications/inventory_and_purchase/inventory/valuation/automatic_valuation.html)
- [OCA Stock Valuation Layer Usage](https://github.com/OCA/stock-logistics-warehouse/tree/17.0/stock_valuation_layer_usage)