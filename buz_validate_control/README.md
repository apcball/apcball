# BUZ Validate Control Module

## Description
This module provides control over who can validate/post documents in Odoo by restricting access to Validate and Post buttons.

## Features
- Hides Validate button in Stock Picking for unauthorized users
- Hides Post button in Account Move for unauthorized users
- Server-side security checks prevent bypassing UI restrictions
- Simple group-based permission management

## Installation
1. Copy the module to your Odoo addons directory
2. Update your module list
3. Install the module from Apps menu

## Configuration
1. Go to Settings > Users & Companies > Groups
2. Find the "Validate Privileged" group under "Validate Control" category
3. Add users who should have validation permissions to this group

## Usage
- Users in the "Validate Privileged" group will see and can use Validate/Post buttons
- Users not in this group will not see these buttons
- Direct API calls are also protected by server-side checks

## Technical Details
- Module overrides `button_validate()` method of `stock.picking`
- Module overrides `action_post()` method of `account.move`
- Uses Odoo's standard group-based security system
- Provides dual-layer protection (UI and server-side)

## Version
17.0.1.0.0

## License
LGPL-3