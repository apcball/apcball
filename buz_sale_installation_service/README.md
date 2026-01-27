# Buz Sale Installation Service

## Overview
This module adds automatic installation service fee management to Odoo 17 sale orders.

## Features
- Add installation fees to products
- Automatically create installation service lines in sale orders
- Sync quantities between product and installation lines
- Separate revenue accounting for installation fees
- Company-level default installation service product
- Protection against manual manipulation of installation lines

## Installation
1. Copy the module to your Odoo addons directory
2. Update the app list: Settings → Apps → Update Apps List
3. Search for "Sale Installation Service"
4. Click Install

## Configuration
1. Go to Settings → Sales → Installation Service Settings
2. Set the default installation service product
3. Configure installation fees on products:
   - Product → Sales tab → Installation Service section
   - Set installation fee amount
   - Optionally set specific installation service product

## Usage
1. Create a sale order
2. Add a product line with installation fee configured
3. Check "Include Installation" checkbox
4. Installation service line will be created automatically
5. Quantity changes sync automatically to installation line

## Technical Details
- Installation lines cannot be edited or deleted directly
- Installation lines are marked with "↳" prefix
- Deletion of product line automatically removes installation line
- Multi-company and multi-currency supported

## Security
- Sales Users: Can view and use installation features
- Sales Managers: Can configure installation fees on products

## Support
For issues or questions, please contact your system administrator.
