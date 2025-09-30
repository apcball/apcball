# Odoo 17 Upgrade Guide for l10n_th_account_tax_report

This module has been upgraded and is compatible with Odoo 17. This document explains the upgrade process and compatibility features.

## Compatibility Features

- All hooks (pre_init_hook, post_init_hook, uninstall_hook) have been updated for Odoo 17 compatibility
- All models maintain compatibility with Odoo 17 API
- All wizards and reports are compatible with Odoo 17
- Dependencies have been verified for Odoo 17
- Database queries are compatible with Odoo 17
- Report generation (PDF, XLSX, TEXT) works correctly in Odoo 17

## Hook Functions

The module includes three hook functions that ensure proper behavior during installation and uninstallation:

1. `pre_init_hook`: Checks dependencies and applies compatibility patches before installation
2. `post_init_hook`: Performs post-installation checks and data initialization
3. `uninstall_hook`: Cleans up resources during uninstallation

## Migration Scripts

Migration scripts are provided in the `migrations/17.0.1.0.1/` directory to handle any necessary data transformations during the upgrade process.

## Installation

To install this module on Odoo 17:

1. Ensure all dependencies are installed
2. Update the module list
3. Install the l10n_th_account_tax_report module
4. The hooks will handle any necessary compatibility adjustments automatically

## Versioning

This module follows Odoo's versioning convention. The version number 17.0.x.y indicates:

- 17: Compatible with Odoo 17.0
- 0: Major version of the module (OCA standard)
- x: Minor version (new features)
- y: Patch version (bug fixes)