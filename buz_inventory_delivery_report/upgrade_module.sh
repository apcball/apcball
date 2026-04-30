#!/bin/bash

# Upgrade buz_inventory_delivery_report module
# This script will upgrade the module to apply the latest changes

echo "============================================"
echo "Upgrading buz_inventory_delivery_report module"
echo "============================================"

# Clear Python cache
echo "Clearing Python cache..."
find /opt/instance1/odoo17/custom-addons/buz_inventory_delivery_report -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find /opt/instance1/odoo17/custom-addons/buz_inventory_delivery_report -type f -name "*.pyc" -delete 2>/dev/null || true

echo ""
echo "✅ Cache cleared successfully"
echo ""
echo "Next steps:"
echo "1. Restart Odoo server"
echo "2. Go to Apps menu"
echo "3. Remove 'Apps' filter"
echo "4. Search for 'buz_inventory_delivery_report'"
echo "5. Click 'Upgrade' button"
echo ""
echo "Or run this command to upgrade via command line:"
echo "python3 /opt/instance1/odoo17/odoo-bin -c /path/to/odoo.conf -d YOUR_DATABASE -u buz_inventory_delivery_report --stop-after-init"
echo ""
echo "============================================"
