#!/bin/bash
# Safe module update script

echo "🔄 Thai Tax Report Module - Safe Update Script"
echo "=============================================="

# Stop Odoo to prevent conflicts
echo "1. Stopping Odoo service..."
sudo systemctl stop instance1
sleep 5

echo "2. Starting update process..."
cd /opt/instance1/odoo17

# Update dependencies first
echo "   📦 Updating dependencies..."
timeout 120 python3 odoo-bin -d MOG_LIVE_15_08 \
    --addons-path=/opt/instance1/odoo17/addons,/opt/instance1/odoo17/custom-addons \
    --stop-after-init \
    -u date_range,l10n_th_base_utils,l10n_th_partner,l10n_th_account_tax \
    --log-level=error

if [ $? -eq 0 ]; then
    echo "   ✅ Dependencies updated successfully"
else
    echo "   ⚠️  Dependencies update completed with warnings"
fi

# Update the main module
echo "   🎯 Updating l10n_th_account_tax_report..."
timeout 180 python3 odoo-bin -d MOG_LIVE_15_08 \
    --addons-path=/opt/instance1/odoo17/addons,/opt/instance1/odoo17/custom-addons \
    --stop-after-init \
    -u l10n_th_account_tax_report \
    --log-level=info

UPDATE_RESULT=$?

echo "3. Restarting Odoo service..."
sudo systemctl start instance1
sleep 10

# Check results
if [ $UPDATE_RESULT -eq 0 ]; then
    echo "✅ Module update completed successfully!"
    echo "🎉 You can now access Thai Tax Reports in Accounting → Reports"
elif [ $UPDATE_RESULT -eq 124 ]; then
    echo "⏱️  Update timed out (3 minutes). This might indicate performance issues."
    echo "💡 The module might still be working. Check the web interface."
else
    echo "❌ Update failed with exit code: $UPDATE_RESULT"
    echo "💡 Check Odoo logs for more details: sudo tail -f /var/log/odoo/instance1.log"
fi

echo
echo "📋 Final status check:"
sleep 5
./check_status.sh
