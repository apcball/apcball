#!/bin/bash
# Final fix script for l10n_th_account_tax_report installation

echo "=== Final Fix for l10n_th_account_tax_report Installation ==="

# 1. Stop all running Odoo processes
echo -e "\n1. Stopping all running Odoo processes..."
sudo pkill -f "odoo.*instance1.conf" || echo "Could not stop processes with sudo, trying without"
pkill -f "odoo.*instance1.conf"
sleep 3  # Wait a bit for processes to stop

# 2. Verify processes were stopped
echo -e "\n2. Verifying processes were stopped..."
if pgrep -f "odoo.*instance1.conf" > /dev/null; then
    echo "⚠ Some Odoo processes are still running, this may prevent module recognition"
    pgrep -f "odoo.*instance1.conf" | xargs -I {} ps -p {} -o pid,cmd
else
    echo "✓ All Odoo processes stopped successfully"
fi

# 3. Check the configuration file explicitly
echo -e "\n3. Verifying configuration file..."
if [ -f "/etc/instance1.conf" ]; then
    echo "✓ Configuration file exists: /etc/instance1.conf"
    
    # Verify custom-addons is in the addons path
    if grep -q "custom-addons" /etc/instance1.conf; then
        echo "✓ /opt/instance1/odoo17/custom-addons is in addons_path"
        
        # Show the exact addons_path line
        echo "Current addons_path:"
        grep "addons_path" /etc/instance1.conf
    else
        echo "✗ /opt/instance1/odoo17/custom-addons is NOT in addons_path in /etc/instance1.conf"
        echo "You need to add it to the addons_path line in /etc/instance1.conf"
        exit 1
    fi
else
    echo "✗ Configuration file /etc/instance1.conf does not exist"
    exit 1
fi

# 4. Check for any duplicate modules that might cause confusion
echo -e "\n4. Checking for potentially conflicting modules..."
CONFLICTING_MODULES=$(find /opt/instance1/odoo17/custom-addons -maxdepth 1 -type d -name "*l10n_th_account_tax*" | grep -v "l10n_th_account_tax_report")
if [ -n "$CONFLICTING_MODULES" ]; then
    echo "⚠ Potential conflicting modules found:"
    echo "$CONFLICTING_MODULES"
    echo ""
    echo "These modules might conflict with l10n_th_account_tax_report:"
    for mod in $CONFLICTING_MODULES; do
        mod_name=$(basename "$mod")
        echo "  - $mod_name"
        
        # Check if they have similar functionality
        if [ -f "$mod/__manifest__.py" ]; then
            mod_desc=$(python3 -c "import ast; manifest_dict={}; exec(open('$mod/__manifest__.py').read(), {'__builtins__': {}}, manifest_dict); print(manifest_dict.get('name', 'Unknown'))" 2>/dev/null)
            echo "    Description: $mod_desc"
        fi
    done
    echo ""
    echo "⚠ If any of these modules provide similar functionality, consider"
    echo "   temporarily renaming or moving them during installation."
else
    echo "✓ No obvious conflicting modules found"
fi

# 5. Check if module is already installed but in an inconsistent state
echo -e "\n5. Checking if module is already partially installed..."
if [ -f "/etc/instance1.conf" ]; then
    DB_NAME=$(grep "^db_name" /etc/instance1.conf | cut -d'=' -f2 | xargs)
    DB_HOST=$(grep "^db_host" /etc/instance1.conf | cut -d'=' -f2 | xargs)  
    DB_USER=$(grep "^db_user" /etc/instance1.conf | cut -d'=' -f2 | xargs)
    DB_PORT=$(grep "^db_port" /etc/instance1.conf | cut -d'=' -f2 | xargs)
    
    if [ -z "$DB_NAME" ]; then
        DB_NAME="odoo"  # default
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
    
    # Try to check database if psql is available
    if command -v psql >/dev/null 2>&1; then
        MODULE_EXISTS=$(psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -t -c "SELECT name FROM ir_module_module WHERE name = 'l10n_th_account_tax_report';" 2>/dev/null | xargs)
        if [ -n "$MODULE_EXISTS" ]; then
            MODULE_STATE=$(psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -t -c "SELECT state FROM ir_module_module WHERE name = 'l10n_th_account_tax_report';" 2>/dev/null | xargs)
            echo "⚠ Module l10n_th_account_tax_report already exists in database with state: $MODULE_STATE"
            
            if [ "$MODULE_STATE" = "uninstalling" ] || [ "$MODULE_STATE" = "to remove" ] || [ "$MODULE_STATE" = "to install" ]; then
                echo "⚠ Module is in an inconsistent state. You may need to:"
                echo "  - Reset its state in the database, or"
                echo "  - Try updating the Apps list in Odoo UI to complete the process"
            fi
        else
            echo "✓ Module l10n_th_account_tax_report is not in the database (this is expected for new installations)"
        fi
    else
        echo "⚠ Cannot check database directly (psql not available)"
        echo "  You may need to check manually if the module exists in the database"
    fi
fi

# 6. Start Odoo with the configuration
echo -e "\n6. Starting Odoo with the configuration..."
echo "You can start Odoo with this command:"
echo "  /opt/instance1/odoo17/odoo-bin -c /etc/instance1.conf"
echo ""
echo "Or if you have a systemd service:"
echo "  sudo systemctl start odoo"  # if this service uses instance1.conf

# 7. Provide final instructions
echo -e "\n=== Final Instructions ==="
echo "1. Start your Odoo server with: /opt/instance1/odoo17/odoo-bin -c /etc/instance1.conf"
echo "2. Wait for the server to fully start up"
echo "3. In your browser, go to your Odoo instance (typically http://localhost:8069)"
echo "4. Log in as administrator"
echo "5. Go to Apps (top left menu)"
echo "6. Click the dropdown menu next to 'Apps' and select 'Update Apps List'"
echo "7. Wait for the update to complete (this may take a minute)"
echo "8. After updating, search for 'Thai Localization' or 'l10n_th_account_tax_report'"
echo "9. If you see the module, click 'Install'"

echo -e "\nIf the module still doesn't appear after updating the Apps list:"
echo "- Check Odoo server logs for errors"
echo "- Verify that all dependency modules are installed"
echo "- Consider restarting the Odoo server completely if it was running before"
echo "- Make sure you are logged in as an administrator"

echo -e "\n=== Fix Process Complete ==="