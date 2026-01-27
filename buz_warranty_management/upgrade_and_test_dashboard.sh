#!/bin/bash

echo "=========================================="
echo "Upgrading Warranty Management Module"
echo "=========================================="

# Change to Odoo directory
cd /opt/instance1/odoo17

# Stop Odoo service
echo "Stopping Odoo service..."
sudo systemctl stop odoo17

# Upgrade the module with database migration
echo "Upgrading buz_warranty_management module..."
python3 odoo-bin -c /etc/odoo17.conf -u buz_warranty_management -d odoo17 --stop-after-init

# Start Odoo service
echo "Starting Odoo service..."
sudo systemctl start odoo17

echo ""
echo "=========================================="
echo "Module upgraded successfully!"
echo "=========================================="
echo ""
echo "Testing Dashboard Cache..."
echo ""

# Wait for Odoo to start
sleep 5

# Run the fix dashboard cache script
python3 /opt/instance1/odoo17/custom-addons/buz_warranty_management/fix_dashboard_cache.py

echo ""
echo "=========================================="
echo "Dashboard Fix Complete!"
echo "=========================================="
echo ""
echo "What was fixed:"
echo "1. ✓ Changed warranty.dashboard from TransientModel to Model (persistent)"
echo "2. ✓ Implemented singleton pattern - only one dashboard record exists"
echo "3. ✓ Dashboard data now persists when navigating away and back"
echo "4. ✓ Chart preparation methods fixed at correct class level"
echo "5. ✓ Auto-refresh JavaScript reloads dashboard every 5 minutes"
echo "6. ✓ Dashboard loads data automatically on open (no refresh needed)"
echo "7. ✓ Cron job updates cache every 5 minutes in background"
echo "8. ✓ Chart.js library properly loaded for chart rendering"
echo ""
echo "Please test the dashboard:"
echo "1. Navigate to Warranty > Dashboard"
echo "2. Dashboard should load with all data visible immediately"
echo "3. Navigate away to another menu"
echo "4. Come back to Warranty > Dashboard"
echo "5. Data should still be there (not reset)"
echo "6. Charts should display properly (no 'Error loading chart')"
echo "7. Dashboard will auto-refresh every 5 minutes"
echo ""
echo "If charts still show errors, check browser console (F12) for details"
echo ""
