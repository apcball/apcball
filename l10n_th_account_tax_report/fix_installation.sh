#!/bin/bash
# Fix script for l10n_th_account_tax_report installation issues

echo "=== Fixing l10n_th_account_tax_report installation issues ==="

# 1. Ensure dependencies exist
echo -e "\n1. Installing/verifying required Python dependencies..."
pip3 install xlsxwriter || echo "Failed to install xlsxwriter, trying with --user"
pip3 install --user xlsxwriter

# 2. Check module directory permissions
echo -e "\n2. Setting proper permissions for module directory..."
chown -R odoo:odoo /opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report/ 2>/dev/null || echo "Could not change ownership to odoo:odoo"
chmod -R 755 /opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report/

# 3. Verify module structure
echo -e "\n3. Verifying module structure..."
if [ ! -f "/opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report/__manifest__.py" ]; then
    echo "ERROR: __manifest__.py not found in module directory"
    exit 1
fi

if [ ! -f "/opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report/__init__.py" ]; then
    echo "ERROR: __init__.py not found in module directory"
    exit 1
fi

# 4. Check for syntax errors in hooks.py
echo -e "\n4. Checking hooks.py for syntax errors..."
python3 -m py_compile /opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report/hooks.py
if [ $? -ne 0 ]; then
    echo "ERROR: Syntax error in hooks.py"
    exit 1
else
    echo "hooks.py syntax is valid ✓"
fi

# 5. Check if required dependent modules are properly installed in Odoo
echo -e "\n5. Checking if dependent modules exist in Odoo addons path..."
PYTHON_PATH=$(which python3)
if [ -n "$ODOO_RC" ] || [ -f "/etc/odoo/odoo.conf" ] || [ -f "$HOME/odoo.conf" ]; then
    CONF_FILE=""
    if [ -f "/etc/odoo/odoo.conf" ]; then
        CONF_FILE="/etc/odoo/odoo.conf"
    elif [ -f "$HOME/odoo.conf" ]; then
        CONF_FILE="$HOME/odoo.conf"
    elif [ -n "$ODOO_RC" ]; then
        CONF_FILE="$ODOO_RC"
    fi
    
    if [ -n "$CONF_FILE" ]; then
        echo "Using configuration file: $CONF_FILE"
        ADDONS_PATH=$(grep "^addons_path" $CONF_FILE | cut -d'=' -f2 | tr -d ' ')
        
        if [ -n "$ADDONS_PATH" ]; then
            IFS=',' read -ra PATHS <<< "$ADDONS_PATH"
            for path in "${PATHS[@]}"; do
                path=$(echo $path | xargs)  # trim whitespace
                if [ -d "$path/l10n_th_base_utils" ]; then
                    echo "l10n_th_base_utils found in $path"
                elif [ -d "$path/../custom-addons/l10n_th_base_utils" ]; then
                    echo "l10n_th_base_utils found in $path/../custom-addons/"
                else
                    echo "WARNING: l10n_th_base_utils not found in addons path: $path"
                fi
                
                if [ -d "$path/l10n_th_partner" ]; then
                    echo "l10n_th_partner found in $path"
                else
                    echo "WARNING: l10n_th_partner not found in addons path: $path"
                fi
                
                if [ -d "$path/l10n_th_account_tax" ]; then
                    echo "l10n_th_account_tax found in $path"
                else
                    echo "WARNING: l10n_th_account_tax not found in addons path: $path"
                fi
                
                if [ -d "$path/date_range" ]; then
                    echo "date_range found in $path"
                else
                    echo "WARNING: date_range not found in addons path: $path"
                fi
                
                if [ -d "$path/report_xlsx_helper" ]; then
                    echo "report_xlsx_helper found in $path"
                else
                    echo "WARNING: report_xlsx_helper not found in addons path: $path"
                fi
            done
        fi
    fi
fi

# 6. Check if module is in the right place for Odoo to find it
echo -e "\n6. Verifying module placement..."
CUSTOM_ADDONS_PATH="/opt/instance1/odoo17/custom-addons"
if [[ ":$ODOO_ADDONS_PATH:" == *":$CUSTOM_ADDONS_PATH:"* ]] || grep -q "custom-addons" /etc/odoo/odoo.conf 2>/dev/null; then
    echo "Module path appears to be in Odoo addons path ✓"
else
    echo "WARNING: Custom addons path may not be in Odoo configuration"
    echo "Make sure your odoo.conf includes: /opt/instance1/odoo17/custom-addons in the addons_path"
fi

echo -e "\n=== Fix script completed ==="
echo "To complete the installation:"
echo "1. Restart your Odoo server"
echo "2. Update your Apps list in Odoo"
echo "3. Search for 'Thai Localization - VAT and Withholding Tax Reports' and install"
echo ""
echo "If you still have issues, run the diagnostic.sh script to get more details."