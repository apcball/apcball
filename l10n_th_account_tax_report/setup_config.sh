#!/bin/bash
# Script to create basic Odoo configuration file for l10n_th_account_tax_report

echo "=== Setting up Odoo Configuration for l10n_th_account_tax_report ==="

# Find where Odoo might be installed
echo -e "\n1. Looking for Odoo installation..."
ODOO_DIR=""
if [ -d "/opt/instance1/odoo17/odoo" ]; then
    ODOO_DIR="/opt/instance1/odoo17/odoo"
    echo "Found Odoo directory: $ODOO_DIR"
elif [ -d "/usr/lib/python3*/site-packages/odoo" ]; then
    ODOO_DIR=$(find /usr/lib -name "odoo" -type d -path "*/site-packages/*" 2>/dev/null | head -n 1)
    echo "Found Odoo in Python packages: $ODOO_DIR"
else
    echo "⚠ Odoo installation directory not found at expected location"
    read -p "Please enter your Odoo installation directory (e.g., /opt/odoo/odoo-bin/../): " -r
    ODOO_DIR="$REPLY"
    if [ ! -d "$ODOO_DIR" ]; then
        echo "Directory does not exist: $ODOO_DIR"
        exit 1
    fi
fi

# Create a basic configuration file
CONFIG_FILE="/etc/odoo/odoo.conf"
echo -e "\n2. Creating configuration file at $CONFIG_FILE..."

# Create the directory if it doesn't exist
sudo mkdir -p /etc/odoo

# Create the basic configuration
sudo tee $CONFIG_FILE > /dev/null << EOF
[options]
# Database configuration
db_name = odoo
db_user = odoo
db_password = odoo
db_host = localhost
db_port = 5432

# Security
admin_passwd = admin

# Addons path - this is critical for your module to be recognized
addons_path = $ODOO_DIR/addons,/opt/instance1/odoo17/custom-addons

# Server configuration
xmlrpc_port = 8069
logfile = /var/log/odoo/odoo-server.log

# Additional options
workers = 0
max_cron_threads = 1

# Other common settings
data_dir = /var/lib/odoo
log_level = info
EOF

# Set proper permissions
sudo chown odoo:odoo $CONFIG_FILE 2>/dev/null || echo "Could not change ownership, using default permissions"
sudo chmod 640 $CONFIG_FILE

echo "✓ Configuration file created at $CONFIG_FILE"
echo "✓ Added /opt/instance1/odoo17/custom-addons to addons_path"

# Create log directory
sudo mkdir -p /var/log/odoo
sudo touch /var/log/odoo/odoo-server.log
sudo chown odoo:odoo /var/log/odoo/odoo-server.log 2>/dev/null || echo "Could not change log file ownership"

# Verify configuration
echo -e "\n3. Verifying configuration..."
if [ -f "$CONFIG_FILE" ]; then
    echo "✓ Configuration file exists"
    
    # Check if our path is in the addons_path
    if grep -q "/opt/instance1/odoo17/custom-addons" "$CONFIG_FILE"; then
        echo "✓ Module path is in addons_path"
    else
        echo "✗ Module path not found in addons_path"
    fi
else
    echo "✗ Configuration file was not created properly"
    exit 1
fi

# Check if Odoo service exists
echo -e "\n4. Checking for Odoo service..."
if systemctl list-units --type=service | grep -q "odoo"; then
    echo "✓ Found Odoo service"
    echo "To restart with new configuration:"
    echo "  sudo systemctl restart odoo"
elif systemctl list-units --type=service | grep -q "odoo-server"; then
    echo "✓ Found Odoo service (odoo-server)"
    echo "To restart with new configuration:"
    echo "  sudo systemctl restart odoo-server"
else
    echo "ℹ Odoo service not found, you may need to start Odoo manually with:"
    echo "  odoo -c $CONFIG_FILE"
fi

echo -e "\n=== Configuration Setup Complete ==="
echo "Next steps:"
echo "1. Ensure PostgreSQL is running: sudo systemctl start postgresql"
echo "2. Restart your Odoo server to apply the new configuration:"
echo "   sudo systemctl restart odoo  # if using systemd service"
echo "   OR"
echo "   Stop any running Odoo process and start with: odoo -c $CONFIG_FILE"
echo "3. In your browser, go to your Odoo instance (typically http://localhost:8069)"
echo "4. Log in as administrator"
echo "5. Go to Apps > Update Apps List"
echo "6. Search for 'Thai Localization - VAT and Withholding Tax Reports' and install"

echo -e "\nNote: If you're still having issues, run: ./enhanced_debug.sh to get more information."