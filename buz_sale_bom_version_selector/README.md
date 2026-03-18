# BOM Version Selector on Sales (Hybrid Mode)

Enhance Sales flow so that users can select a specific BOM version on the entire Sale Order or override it on each Sale Order Line.

## Features
- **Hybrid BOM Selection**: 
  - **Header Level**: Set a default BOM Version for the entire order, similar to a Pricelist.
  - **Line Level**: Optionally override the default BOM on specific lines.
- **Auto-Sync Logic**: Changing the header BOM updates all draft lines unless they have been manually overridden. 
- **Visual Indicators**: Overridden lines display a warning color on the BOM field to stand out.
- **Manufacturing Integration**: The effective BOM (line override or header default) is automatically passed to the created Manufacturing Order.
- **Kit Integration**: Delivery orders explode using the effective Kit BOM instead of the default one.
- **Validation**: 
  - Prevents SO confirmation if a product has multiple BOMs but none are selected.
  - Blocks confirmation if a Kit BOM is assigned to an incompatible product type.
- **Chatter Logging**: Generates a consolidated log of applied BOM versions upon confirmation.

## Requirements
- Odoo 17 (Community or Enterprise)
- Modules: `sale`, `stock`, `mrp`

## Installation
1. Copy the `buz_sale_bom_version_selector` folder to your custom addons directory.
2. Update the app list in Odoo.
3. Install or Upgrade the module.
