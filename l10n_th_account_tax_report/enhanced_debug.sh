#!/bin/bash
# Enhanced debugging script for l10n_th_account_tax_report installation

echo "=== Enhanced Debugging for l10n_th_account_tax_report ==="

# Check if there are any Odoo log files
echo -e "\n1. Looking for Odoo log files..."
LOG_FILES=("/var/log/odoo/odoo-server.log" "$HOME/odoo-server.log" "./odoo-server.log" "/tmp/odoo-server.log")

for log_file in "${LOG_FILES[@]}"; do
    if [ -f "$log_file" ]; then
        echo "Found log file: $log_file"
        # Look for recent errors related to our module
        echo "Recent errors related to l10n_th_account_tax_report:"
        grep -i "l10n_th_account_tax_report\|ImportError\|SyntaxError\|Traceback" "$log_file" | tail -20
        break
    fi
done

if [ ! -f "/var/log/odoo/odoo-server.log" ] && [ ! -f "$HOME/odoo-server.log" ] && [ ! -f "./odoo-server.log" ] && [ ! -f "/tmp/odoo-server.log" ]; then
    echo "No standard log files found. Please check your Odoo configuration."
fi

# Check if the module is in the addons path
echo -e "\n2. Checking if module path is in addons path..."
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
        echo "Configuration file: $CONF_FILE"
        ADDONS_PATH=$(grep "^addons_path" $CONF_FILE | cut -d'=' -f2 | xargs)  # trim whitespace
        echo "Current addons_path: $ADDONS_PATH"
        
        if [[ ":$ADDONS_PATH:" == *":/opt/instance1/odoo17/custom-addons:"* ]]; then
            echo "✓ Module path is in addons_path"
        else
            echo "✗ Module path is NOT in addons_path"
            echo "You need to add /opt/instance1/odoo17/custom-addons to your addons_path in $CONF_FILE"
        fi
    fi
else
    echo "No Odoo configuration file found"
fi

# Check the manifest file format specifically
echo -e "\n3. Checking manifest file syntax..."
python3 -c "
import ast
import json
try:
    with open('/opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report/__manifest__.py', 'r') as f:
        content = f.read()
    # The manifest file contains a dictionary, not a Python file we can compile
    # We'll evaluate it carefully
    manifest_dict = {}
    exec(content, {'__builtins__': {}}, manifest_dict)
    print('✓ Manifest file syntax is valid')
    print('Module name:', manifest_dict.get('name', 'NOT FOUND'))
    print('Module version:', manifest_dict.get('version', 'NOT FOUND'))
    print('Dependencies:', manifest_dict.get('depends', []))
except Exception as e:
    print('✗ Error in manifest file:', str(e))
"

# Check if required dependencies are installed in the system
echo -e "\n4. Checking system dependencies..."
which python3 > /dev/null && echo "✓ Python3 found" || echo "✗ Python3 not found"
which pip3 > /dev/null && echo "✓ Pip3 found" || echo "✗ Pip3 not found"

# Check if required Python packages are available
echo -e "\n5. Testing Python imports..."
python3 -c "import xlsxwriter" 2>/dev/null && echo "✓ xlsxwriter import successful" || echo "✗ xlsxwriter import failed"
python3 -c "import odoo" 2>/dev/null && echo "✓ odoo import successful" || echo "✗ odoo import failed"

# Check for circular dependencies or import issues in the module
echo -e "\n6. Testing module imports..."
python3 -c "
import sys
sys.path.insert(0, '/opt/instance1/odoo17/custom-addons')
try:
    # Change to the module directory to simulate Odoo's import behavior
    import os
    os.chdir('/opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report')
    
    # Test importing the main files
    import __init__
    print('✓ __init__.py imported successfully')
    
    import hooks
    print('✓ hooks.py imported successfully')
    
    import models
    print('✓ models imported successfully')
    
    import wizard
    print('✓ wizard imported successfully')
    
    import reports
    print('✓ reports imported successfully')
    
except ImportError as e:
    print('✗ Import error:', str(e))
except Exception as e:
    print('✗ Other error during import:', str(e))
"

# Check file permissions
echo -e "\n7. Checking file permissions..."
if [ -r "/opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report/__manifest__.py" ]; then
    echo "✓ __manifest__.py is readable"
else
    echo "✗ __manifest__.py is not readable"
fi

# Check if there are any __pycache__ directories that might cause issues
echo -e "\n8. Checking for Python cache files that might cause issues..."
if ls /opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report/__pycache__ 2>/dev/null; then
    echo "⚠ Found __pycache__ directory - this might cause import issues"
    echo "Consider removing it: rm -rf /opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report/__pycache__"
else
    echo "✓ No __pycache__ directory found"
fi

for dir in models wizard reports; do
    if ls /opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report/$dir/__pycache__ 2>/dev/null; then
        echo "⚠ Found $dir/__pycache__ directory - this might cause import issues"
    fi
done

echo -e "\n=== Enhanced Debugging Complete ==="
echo "If installation is still failing:"
echo "1. Check if you can see the module in your Apps list after updating the Apps list"
echo "2. Check the Odoo server logs while trying to install"
echo "3. Make sure you are installing as an administrator"
echo "4. Verify that all dependencies are installed in your Odoo instance"