# Installation Troubleshooting Guide for l10n_th_account_tax_report

## Issue Identified
The main issue preventing installation is that the module's directory path (`/opt/instance1/odoo17/custom-addons`) is not in Odoo's `addons_path` configuration. Without this, Odoo cannot discover the module.

## Required Configuration
1. Create an Odoo configuration file (typically at `/etc/odoo/odoo.conf`) with the correct `addons_path`

## Steps to Fix Installation

### Step 1: Create Configuration File
Create `/etc/odoo/odoo.conf` with this content:

```
[options]
# Database configuration
db_name = odoo
db_user = odoo
db_password = odoo
db_host = localhost
db_port = 5432

# Security
admin_passwd = admin

# Addons path - CRITICAL: must include your custom addons directory
addons_path = /opt/instance1/odoo17/odoo/addons,/opt/instance1/odoo17/custom-addons

# Server configuration
xmlrpc_port = 8069
logfile = /var/log/odoo/odoo-server.log

# Additional options
workers = 0
max_cron_threads = 1

# Other common settings
data_dir = /var/lib/odoo
log_level = info
```

### Step 2: Create Log Directory
```bash
sudo mkdir -p /var/log/odoo
sudo touch /var/log/odoo/odoo-server.log
```

### Step 3: Set Permissions
```bash
sudo chown odoo:odoo /etc/odoo/odoo.conf
sudo chmod 640 /etc/odoo/odoo.conf
```

### Step 4: Restart Odoo
Restart your Odoo server to apply the configuration changes.

### Step 5: Install Module in Odoo UI
1. Access your Odoo instance (typically http://localhost:8069)
2. Log in as administrator
3. Go to Apps (top menu)
4. Click the dropdown next to 'Apps' and select 'Update Apps List'
5. Wait for the update to complete
6. Search for 'Thai Localization - VAT and Withholding Tax Reports'
7. Click Install

## Verification Steps Completed
- [x] Fixed Python syntax in hooks.py
- [x] Cleaned up Python cache files
- [x] Verified all module files have correct syntax
- [x] Created installation troubleshooting scripts
- [x] Identified the core configuration issue

## Additional Tools Provided
This module directory now includes:
- `diagnostic.sh` - Diagnose installation issues
- `enhanced_debug.sh` - Detailed debugging
- `specific_install_fix.sh` - Targeted fixes
- `setup_config.sh` - Configuration setup script
- `manual_config_setup.md` - Manual instructions
- `final_activation.sh` - Final activation steps
- `upgrade_to_odoo17.sh` - Upgrade script

The module code itself is now properly configured for Odoo 17. The only remaining requirement is to ensure your Odoo server is configured with the correct `addons_path` that includes `/opt/instance1/odoo17/custom-addons`.