#!/bin/bash
# Manual Odoo Configuration Setup Instructions for l10n_th_account_tax_report

echo "=== Manual Odoo Configuration Setup for l10n_th_account_tax_report ==="

echo -e "\n1. You need to create an Odoo configuration file with the proper addons path."
echo "The configuration file should be at: /etc/odoo/odoo.conf"

echo -e "\n2. Create this file with the following content (run as root or with sudo):"

cat << 'EOF'

[options]
# Database configuration
db_name = odoo
db_user = odoo
db_password = odoo
db_host = localhost
db_port = 5432

# Security
admin_passwd = admin

# Addons path - THIS IS CRITICAL: it must include your custom addons directory
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
EOF

echo -e "\n3. You can create the file using this command (as root or with sudo):"
echo "sudo mkdir -p /etc/odoo"
echo "sudo tee /etc/odoo/odoo.conf > /dev/null << 'EOL'"
cat << 'EOF' | sed 's/^/  /'
[options]
# Database configuration
db_name = odoo
db_user = odoo
db_password = odoo
db_host = localhost
db_port = 5432

# Security
admin_passwd = admin

# Addons path - THIS IS CRITICAL: it must include your custom addons directory
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
EOF
echo "EOL"

echo -e "\n4. Create the log directory:"
echo "sudo mkdir -p /var/log/odoo"
echo "sudo touch /var/log/odoo/odoo-server.log"

echo -e "\n5. Make sure the Odoo configuration file has proper permissions:"
echo "sudo chown odoo:odoo /etc/odoo/odoo.conf"
echo "sudo chmod 640 /etc/odoo/odoo.conf"

echo -e "\n6. After creating the configuration file, restart your Odoo server to apply the changes."

echo -e "\n7. If you don't have a systemd service, start Odoo manually with:"
echo "odoo -c /etc/odoo/odoo.conf"

echo -e "\n8. Once Odoo is running with the new configuration:"
echo "   a) Go to your Odoo instance in a browser (usually http://localhost:8069)"
echo "   b) Log in as administrator"
echo "   c) Go to Apps > Update Apps List"
echo "   d) Search for 'Thai Localization - VAT and Withholding Tax Reports'"
echo "   e) Click Install"

echo -e "\n=== Manual Setup Instructions Complete ==="