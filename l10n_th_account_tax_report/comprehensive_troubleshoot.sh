#!/bin/bash
# Comprehensive troubleshooting and installation fix script for l10n_th_account_tax_report

echo "=== Comprehensive Troubleshooting for l10n_th_account_tax_report ==="

# Function to ask for user input with a default
ask_with_default() {
    local prompt="$1"
    local default="$2"
    local result
    
    read -p "$prompt (default: $default): " result
    echo "${result:-$default}"
}

# 1. Find Odoo configuration
echo -e "\n1. Finding Odoo configuration..."
ODOO_CONF=""
if [ -f "/etc/odoo/odoo.conf" ]; then
    ODOO_CONF="/etc/odoo/odoo.conf"
    echo "Found configuration file: $ODOO_CONF"
elif [ -f "$HOME/odoo.conf" ]; then
    ODOO_CONF="$HOME/odoo.conf"
    echo "Found configuration file: $ODOO_CONF"
elif [ -n "$ODOO_RC" ]; then
    ODOO_CONF="$ODOO_RC"
    echo "Found configuration file: $ODOO_CONF"
else
    echo "No standard Odoo configuration file found."
    ODOO_CONF_INPUT=$(ask_with_default "Please enter the path to your Odoo configuration file" "/etc/odoo/odoo.conf")
    if [ -f "$ODOO_CONF_INPUT" ]; then
        ODOO_CONF="$ODOO_CONF_INPUT"
        echo "Using configuration file: $ODOO_CONF"
    else
        echo "Configuration file does not exist: $ODOO_CONF_INPUT"
        read -p "Do you want to create a basic configuration file? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            # Create a basic configuration
            DB_NAME=$(ask_with_default "Database name" "odoo")
            DB_USER=$(ask_with_default "Database user" "odoo")
            DB_PASSWORD=$(ask_with_default "Database password" "odoo")
            ADMIN_PASSWORD=$(ask_with_default "Master/Secret password" "admin")
            
            cat > $ODOO_CONF_INPUT << EOF
[options]
; Database
db_name = $DB_NAME
db_user = $DB_USER
db_password = $DB_PASSWORD
db_host = localhost
db_port = 5432

; Security
admin_passwd = $ADMIN_PASSWORD

; Addons
addons_path = /opt/instance1/odoo17/odoo/addons,/opt/instance1/odoo17/custom-addons

; Server
xmlrpc_port = 8069
logfile = /var/log/odoo/odoo-server.log

; Other
workers = 0
max_cron_threads = 1
EOF
            echo "Basic configuration file created at $ODOO_CONF_INPUT"
            ODOO_CONF="$ODOO_CONF_INPUT"
        else
            echo "Cannot proceed without a valid Odoo configuration file."
            exit 1
        fi
    fi
fi

# 2. Check and fix addons_path in the configuration
echo -e "\n2. Checking addons_path in configuration..."
if [ -n "$ODOO_CONF" ]; then
    ADDONS_PATH=$(grep "^addons_path" $ODOO_CONF | cut -d'=' -f2 | xargs)
    
    if [[ ":$ADDONS_PATH:" == *":/opt/instance1/odoo17/custom-addons:"* ]]; then
        echo "✓ Module path is already in addons_path"
    else
        echo "⚠ Module path is NOT in addons_path"
        read -p "Do you want to add it to the configuration file? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            # Backup the configuration file first
            cp "$ODOO_CONF" "$ODOO_CONF.backup.$(date +%Y%m%d_%H%M%S)"
            echo "Backup created: $ODOO_CONF.backup.$(date +%Y%m%d_%H%M%S)"
            
            # Update the addons_path
            if [ -n "$ADDONS_PATH" ]; then
                # Append our path to existing paths
                NEW_ADDONS_PATH="$ADDONS_PATH,/opt/instance1/odoo17/custom-addons"
            else
                # Set our path as the addons path
                NEW_ADDONS_PATH="/opt/instance1/odoo17/odoo/addons,/opt/instance1/odoo17/custom-addons"
            fi
            
            sed -i "s|^addons_path[[:space:]]*=.*|addons_path = $NEW_ADDONS_PATH|; t; /addons_path/!s/^/\naddons_path = $NEW_ADDONS_PATH\n/" "$ODOO_CONF"
            echo "Updated addons_path in $ODOO_CONF"
            echo "New addons_path: $NEW_ADDONS_PATH"
        else
            echo "Please manually add /opt/instance1/odoo17/custom-addons to your addons_path in $ODOO_CONF"
        fi
    fi
fi

# 3. Verify module structure
echo -e "\n3. Verifying module structure..."
MODULE_DIR="/opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report"
if [ -d "$MODULE_DIR" ]; then
    echo "✓ Module directory exists"
else
    echo "✗ Module directory does not exist"
    exit 1
fi

REQUIRED_FILES=("$MODULE_DIR/__manifest__.py" "$MODULE_DIR/__init__.py" "$MODULE_DIR/hooks.py")
for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "✓ $file exists"
    else
        echo "✗ $file missing"
        exit 1
    fi
done

# 4. Check syntax of Python files again
echo -e "\n4. Verifying Python file syntax..."
for py_file in "$MODULE_DIR"/*.py; do
    if [ -f "$py_file" ]; then 
        python3 -m py_compile "$py_file" 2>/dev/null && echo "✓ $(basename $py_file) syntax OK" || echo "✗ $(basename $py_file) has syntax errors"
    fi
done

for sub_dir in models wizard reports; do
    if [ -d "$MODULE_DIR/$sub_dir" ]; then
        for py_file in "$MODULE_DIR/$sub_dir"/*.py; do
            if [ -f "$py_file" ]; then 
                python3 -m py_compile "$py_file" 2>/dev/null && echo "✓ $sub_dir/$(basename $py_file) syntax OK" || echo "✗ $sub_dir/$(basename $py_file) has syntax errors"
            fi
        done
    fi
done

# 5. Check permissions
echo -e "\n5. Setting proper permissions..."
chmod 644 "$MODULE_DIR"/*.py
chmod 644 "$MODULE_DIR"/models/*.py
chmod 644 "$MODULE_DIR"/wizard/*.py
chmod 644 "$MODULE_DIR"/reports/*.py

# 6. Check if there are XML files that should exist
echo -e "\n6. Checking required XML files..."
XML_FILES=(
    "$MODULE_DIR/security/ir.model.access.csv"
    "$MODULE_DIR/data/paper_format.xml"
    "$MODULE_DIR/data/report_data.xml"
    "$MODULE_DIR/views/res_company_views.xml"
    "$MODULE_DIR/views/res_config_settings_views.xml"
    "$MODULE_DIR/wizard/tax_report_wizard_view.xml"
    "$MODULE_DIR/wizard/withholding_tax_report_wizard_view.xml"
    "$MODULE_DIR/reports/templates/tax_report.xml"
    "$MODULE_DIR/views/account_menu.xml"
)

for xml_file in "${XML_FILES[@]}"; do
    if [ -f "$xml_file" ]; then
        echo "✓ $xml_file exists"
    else
        echo "⚠ $xml_file missing - this might cause installation issues"
    fi
done

# 7. Final instructions
echo -e "\n=== Final Steps ==="
echo "To complete the installation:"
echo "1. Ensure your Odoo server is stopped"
echo "2. Verify the configuration file $ODOO_CONF has the correct addons_path"
echo "3. Start your Odoo server with the updated configuration"
echo "4. In your browser, go to your Odoo instance (typically http://localhost:8069)"
echo "5. Log in as administrator"
echo "6. Go to Apps (top left)"
echo "7. Click the dropdown next to 'Apps' and select 'Update Apps List'"
echo "8. Wait for the update to complete"
echo "9. Search for 'Thai Localization - VAT and Withholding Tax Reports'"
echo "10. Click 'Install'"

echo -e "\nTroubleshooting tips:"
echo "- If the module doesn't appear after updating the Apps list, double-check:"
echo "  a) The configuration file has the correct addons_path"
echo "  b) All required modules are installed (l10n_th_base_utils, l10n_th_partner, etc.)"
echo "  c) The Odoo server was restarted after configuration changes"
echo "- Check the Odoo server logs for any errors during startup"
echo "- Make sure the 'Show Apps' option is enabled in the Apps menu"

echo -e "\nIf issues persist, run: ./enhanced_debug.sh to get more detailed information."

echo -e "\n=== Troubleshooting Complete ==="