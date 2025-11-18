#!/bin/bash
# Script to fix the landed cost constraint validation error
# This upgrades the stock_fifo_by_location module to apply the constraint fix

DATABASE="MOG_LIVE_15_08"
MODULE="stock_fifo_by_location"
ODOO_BIN="/opt/instance1/odoo17/odoo-bin"
ODOO_VENV="/opt/instance1/odoo17-venv/bin/python3"
ODOO_CONF="/etc/instance1.conf"

echo "========================================"
echo "Fixing Landed Cost Constraint Issue"
echo "========================================"
echo ""
echo "Database: $DATABASE"
echo "Module: $MODULE"
echo ""

# Stop the Odoo service
echo "Stopping Odoo service..."
sudo systemctl stop instance1

# Upgrade the module
echo ""
echo "Upgrading module to apply constraint fix..."
sudo -u mogenit $ODOO_VENV $ODOO_BIN \
    -c $ODOO_CONF \
    -d $DATABASE \
    -u $MODULE \
    --stop-after-init

if [ $? -eq 0 ]; then
    echo ""
    echo "✓ Module upgrade completed successfully!"
    echo ""
    
    # Verify the constraint
    echo "Verifying constraint..."
    sudo -u postgres psql $DATABASE -c "
        SELECT 
            conname as constraint_name,
            CASE confdeltype 
                WHEN 'c' THEN 'CASCADE'
                WHEN 'n' THEN 'SET NULL'
                WHEN 'r' THEN 'RESTRICT'
                WHEN 'a' THEN 'NO ACTION'
            END as on_delete_action
        FROM pg_constraint
        WHERE conname = 'stock_valuation_layer_landed__valuation_adjustment_line_id_fkey';
    "
    
    echo ""
    echo "✓ Fix has been applied successfully!"
else
    echo ""
    echo "✗ Error during module upgrade!"
    exit 1
fi

# Start the Odoo service
echo ""
echo "Starting Odoo service..."
sudo systemctl start instance1

echo ""
echo "Waiting for Odoo to start..."
sleep 5

# Check service status
sudo systemctl status instance1 --no-pager | head -15

echo ""
echo "========================================"
echo "Fix completed!"
echo "========================================"
echo ""
echo "The constraint has been updated from RESTRICT to CASCADE."
echo "You can now delete landed cost records without validation errors."
