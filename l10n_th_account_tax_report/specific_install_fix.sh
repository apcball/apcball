#!/bin/bash
# Specific installation fix for l10n_th_account_tax_report

echo "=== Specific Installation Fix for l10n_th_account_tax_report ==="

# 1. Clean up any Python cache files
echo "1. Cleaning up Python cache files..."
find /opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || echo "No __pycache__ directories found to remove"
find /opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report -name "*.pyc" -delete 2>/dev/null || echo "No .pyc files found to delete"

# 2. Check if Odoo configuration exists and if module path is in addons_path
echo -e "\n2. Looking for Odoo configuration..."
ODOO_CONF=""
if [ -f "/etc/odoo/odoo.conf" ]; then
    ODOO_CONF="/etc/odoo/odoo.conf"
elif [ -f "$HOME/odoo.conf" ]; then
    ODOO_CONF="$HOME/odoo.conf"
elif [ -n "$ODOO_RC" ]; then
    ODOO_CONF="$ODOO_RC"
fi

if [ -n "$ODOO_CONF" ]; then
    echo "Found configuration file: $ODOO_CONF"
    
    # Extract addons_path
    ADDONS_PATH=$(grep "^addons_path" $ODOO_CONF | cut -d'=' -f2 | xargs)  # trim whitespace
    echo "Current addons_path: $ADDONS_PATH"
    
    # Check if our path is in addons_path
    if [[ ":$ADDONS_PATH:" == *":/opt/instance1/odoo17/custom-addons:"* ]]; then
        echo "✓ Module path is already in addons_path"
    else
        echo "⚠ Module path is NOT in addons_path"
        echo "You need to add /opt/instance1/odoo17/custom-addons to your addons_path in $ODOO_CONF"
        echo "Edit the file and add /opt/instance1/odoo17/custom-addons to the addons_path line, separated by commas"
        echo "Example: addons_path = /path/to/core/addons,/opt/instance1/odoo17/custom-addons"
    fi
else
    echo "⚠ No Odoo configuration file found"
    echo "Look for odoo.conf in these common locations:"
    echo "  - /etc/odoo/odoo.conf"
    echo "  - $HOME/odoo.conf"
    echo "  - Or check if ODOO_RC environment variable is set"
    echo ""
    echo "You'll need to add /opt/instance1/odoo17/custom-addons to the addons_path in your configuration file."
fi

# 3. Check if required dependent modules are installed in Odoo database
echo -e "\n3. Checking for required dependent modules in your Odoo database..."
if [ -n "$ODOO_CONF" ]; then
    # Extract database info from config
    DB_NAME=$(grep "^db_name" $ODOO_CONF | cut -d'=' -f2 | xargs)
    DB_HOST=$(grep "^db_host" $ODOO_CONF | cut -d'=' -f2 | xargs)
    DB_USER=$(grep "^db_user" $ODOO_CONF | cut -d'=' -f2 | xargs)
    DB_PORT=$(grep "^db_port" $ODOO_CONF | cut -d'=' -f2 | xargs)
    
    if [ -z "$DB_NAME" ]; then
        echo "⚠ Database name not found in config. Using default 'odoo' or enter manually."
        read -p "Enter your Odoo database name (or press Enter for 'odoo'): " -r
        if [ -z "$REPLY" ]; then
            DB_NAME="odoo"
        else
            DB_NAME="$REPLY"
        fi
    fi
    
    if [ -z "$DB_HOST" ]; then
        DB_HOST="localhost"
    fi
    
    if [ -z "$DB_USER" ]; then
        DB_USER="odoo"
    fi
    
    if [ -z "$DB_PORT" ]; then
        DB_PORT="5432"
    fi
    
    # Attempt to check if required modules are installed
    echo "Checking database $DB_NAME at $DB_HOST:$DB_PORT with user $DB_USER..."
    
    # Check if psql is available
    if command -v psql >/dev/null 2>&1; then
        echo "Checking if required modules are installed in database..."
        psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -c "
        SELECT name, state 
        FROM ir_module_module 
        WHERE name IN ('l10n_th_base_utils', 'l10n_th_partner', 'l10n_th_account_tax', 'date_range', 'report_xlsx_helper')
        ORDER BY name;
        " 2>/dev/null || echo "Could not connect to database. Please check your database settings."
    else
        echo "psql command not found. Cannot check database directly."
        echo "You'll need to manually check if these modules are installed in your Odoo instance:"
        echo "  - l10n_th_base_utils"
        echo "  - l10n_th_partner" 
        echo "  - l10n_th_account_tax"
        echo "  - date_range"
        echo "  - report_xlsx_helper"
        echo "  - account"
    fi
else
    echo "Cannot check database without configuration file."
fi

# 4. Verify file permissions
echo -e "\n4. Setting proper file permissions..."
chown -R odoo:odoo /opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report/ 2>/dev/null || echo "Could not change ownership. Make sure files are readable by Odoo user."
chmod -R 644 /opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report/*.py 2>/dev/null
chmod -R 755 /opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report/ 2>/dev/null

# 5. Check the manifest syntax again
echo -e "\n5. Verifying manifest file integrity..."
if python3 -c "
import ast
with open('/opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report/__manifest__.py', 'r') as f:
    content = f.read()
# Extract the dict part and ensure it's properly formatted
manifest_dict = {}
exec(content, {'__builtins__': {'__import__': __import__}}, manifest_dict)
print('✓ Manifest file is syntactically correct')
" ; then
    echo "✓ Manifest file is valid"
else
    echo "✗ Error in manifest file syntax"
    exit 1
fi

# 6. Final installation steps reminder
echo -e "\n=== Installation Steps ==="
echo "After addressing the configuration issues above:"
echo "1. Restart your Odoo server to pick up configuration changes"
echo "2. In Odoo web interface:"
echo "   a) Go to Apps (make sure you're logged in as admin)"
echo "   b) Click on the dropdown menu next to 'Apps' and select 'Update Apps List'"
echo "   c) Wait for the update to complete"
echo "   d) Search for 'Thai Localization - VAT and Withholding Tax Reports'"
echo "   e) Click 'Install'"
echo ""
echo "If the module still doesn't appear in your Apps list after updating:"
echo "- Double check that /opt/instance1/odoo17/custom-addons is in your addons_path"
echo "- Verify that Odoo has read permissions on the module directory"
echo "- Check that your Odoo server is running with the correct configuration"
echo "- Ensure all dependency modules are installed and up-to-date"

echo -e "\n=== Fix Process Complete ==="