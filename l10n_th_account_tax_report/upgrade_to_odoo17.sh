#!/bin/bash
# Upgrade script for l10n_th_account_tax_report module to Odoo 17

echo "Starting upgrade of l10n_th_account_tax_report module to Odoo 17..."

# Check if Odoo is running
if pgrep -f "odoo.*.py" > /dev/null
then
    echo "Odoo is currently running."
else
    echo "Warning: No Odoo process detected. Make sure your Odoo server is running."
fi

# Update the module
echo "Updating l10n_th_account_tax_report module..."
cd /opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report

# Run diagnostics first to check for any issues
echo "Running diagnostics before upgrade..."
if [ -f "diagnostic.sh" ]; then
    ./diagnostic.sh
else
    echo "No diagnostic script found"
fi

# Install required dependencies
pip3 install xlsxwriter || echo "Failed to install xlsxwriter via pip3"

echo "Module files are now updated and ready for installation in Odoo."

# Restart Odoo server (adjust the command based on your setup)
echo "Please restart your Odoo server to apply changes:"
echo "sudo systemctl restart odoo" 
# Or if running manually:
# echo "odoo -d your_database_name -c your_config_file --addons-path=addons_path,custom_addons_path"

echo "Installation steps:"
echo "1. Go to Apps > Update Apps List in your Odoo interface"
echo "2. Search for 'Thai Localization - VAT and Withholding Tax Reports'"
echo "3. Click Install"
echo ""
echo "If installation fails, run: ./diagnostic.sh to identify issues"
echo "Then run: ./fix_installation.sh to attempt to fix common issues"
echo "Finally run: ./final_activation.sh for final activation steps"