#!/bin/bash
# Final activation script for l10n_th_account_tax_report on Odoo 17

echo "=== Final Activation: l10n_th_account_tax_report for Odoo 17 ==="

# Function to check if Odoo is running
is_odoo_running() {
    pgrep -f "odoo.*.py" > /dev/null
    return $?
}

# Check if Odoo is currently running
if is_odoo_running; then
    echo "✓ Odoo is currently running"
    ODOO_RUNNING=true
else
    echo "⚠ Odoo is not currently running"
    ODOO_RUNNING=false
fi

# Check module integrity
echo -e "\n1. Verifying module integrity..."
if [ ! -f "/opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report/__manifest__.py" ]; then
    echo "ERROR: __manifest__.py not found"
    exit 1
fi

if [ ! -f "/opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report/hooks.py" ]; then
    echo "ERROR: hooks.py not found"
    exit 1
fi

# Check Python syntax
echo -e "\n2. Checking Python syntax..."
python3 -m py_compile /opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report/__init__.py
if [ $? -ne 0 ]; then
    echo "ERROR: Syntax error in __init__.py"
    exit 1
fi

python3 -m py_compile /opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report/hooks.py
if [ $? -ne 0 ]; then
    echo "ERROR: Syntax error in hooks.py"
    exit 1
fi

echo -e "\n3. Checking dependencies..."
pip3 list | grep -i xlsxwriter > /dev/null
if [ $? -ne 0 ]; then
    echo "Installing xlsxwriter..."
    pip3 install xlsxwriter
else
    echo "✓ xlsxwriter is already installed"
fi

# Try to install the module in Odoo
if [ "$ODOO_RUNNING" = true ]; then
    echo -e "\n4. Odoo is running. Please install the module via Odoo interface:"
    echo "   a) Go to Apps > Update Apps List"
    echo "   b) Search for 'Thai Localization - VAT and Withholding Tax Reports'"
    echo "   c) Click Install"
else
    echo -e "\n4. Starting Odoo to install the module..."
    echo "⚠ Manual action required: Please start your Odoo server and install via web interface"
fi

# Check if Odoo configuration exists
if [ -f "/etc/odoo/odoo.conf" ]; then
    echo -e "\n5. Found Odoo configuration at /etc/odoo/odoo.conf"
    echo "Please ensure your addons_path includes: /opt/instance1/odoo17/custom-addons"
    grep -q "custom-addons" /etc/odoo/odoo.conf && echo "✓ custom-addons path found in configuration" || echo "⚠ custom-addons path not found in configuration"
elif [ -f "$HOME/odoo.conf" ]; then
    echo -e "\n5. Found Odoo configuration at $HOME/odoo.conf"
    echo "Please ensure your addons_path includes: /opt/instance1/odoo17/custom-addons"
    grep -q "custom-addons" $HOME/odoo.conf && echo "✓ custom-addons path found in configuration" || echo "⚠ custom-addons path not found in configuration"
else
    echo -e "\n5. No standard Odoo configuration file found"
    echo "Please ensure your Odoo configuration includes: /opt/instance1/odoo17/custom-addons in the addons_path"
fi

echo -e "\n=== Activation Complete ==="
echo "The module is ready for installation in Odoo."
echo ""
echo "Next steps:"
echo "1. Ensure your Odoo server is running"
echo "2. Go to your Odoo instance in a web browser"
echo "3. Log in as an administrator"
echo "4. Go to Apps > Update Apps List"
echo "5. Search for 'Thai Localization - VAT and Withholding Tax Reports'"
echo "6. Click Install"
echo ""
echo "If you encounter issues during installation, run the diagnostic.sh script to identify problems."