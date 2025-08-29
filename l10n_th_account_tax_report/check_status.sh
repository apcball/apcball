#!/bin/bash
# Simple module status checker

echo "🔍 Checking l10n_th_account_tax_report installation status..."

# Method 1: Check via filesystem
echo "1. Module files check:"
if [ -f "/opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report/__manifest__.py" ]; then
    echo "   ✅ Module files exist"
else
    echo "   ❌ Module files missing"
    exit 1
fi

# Method 2: Check via Odoo logs
echo "2. Installation logs check:"
if sudo grep -q "Module l10n_th_account_tax_report loaded" /var/log/odoo/instance1.log; then
    echo "   ✅ Module has been loaded before"
    # Get last load time
    LAST_LOAD=$(sudo grep "Module l10n_th_account_tax_report loaded" /var/log/odoo/instance1.log | tail -1 | cut -d' ' -f1-2)
    echo "   📅 Last loaded: $LAST_LOAD"
else
    echo "   ❌ No successful load found in logs"
fi

# Method 3: Check for errors
echo "3. Error logs check:"
ERROR_COUNT=$(sudo grep -c "l10n_th_account_tax_report.*ERROR\|ERROR.*l10n_th_account_tax_report" /var/log/odoo/instance1.log 2>/dev/null || echo "0")
if [ "$ERROR_COUNT" -eq 0 ]; then
    echo "   ✅ No errors found in logs"
else
    echo "   ⚠️  Found $ERROR_COUNT errors in logs"
    echo "   Last few errors:"
    sudo grep "l10n_th_account_tax_report.*ERROR\|ERROR.*l10n_th_account_tax_report" /var/log/odoo/instance1.log | tail -3
fi

# Method 4: Check web accessibility
echo "4. Web interface check:"
if curl -s "http://localhost:8069/l10n_th_account_tax_report/static/description/icon.png" >/dev/null 2>&1; then
    echo "   ✅ Module static files accessible via web"
else
    echo "   ❌ Module static files not accessible via web"
fi

echo
echo "📋 Summary:"
echo "   - Module files: Present"
echo "   - Installation logs: $(if sudo grep -q "Module l10n_th_account_tax_report loaded" /var/log/odoo/instance1.log; then echo "Found"; else echo "Not found"; fi)"
echo "   - Errors: $ERROR_COUNT"
echo "   - Web access: $(if curl -s "http://localhost:8069/l10n_th_account_tax_report/static/description/icon.png" >/dev/null 2>&1; then echo "Working"; else echo "Not working"; fi)"

echo
echo "💡 To install/reinstall the module:"
echo "   1. Via web interface: Go to Apps → Search 'Thai Tax' → Install"
echo "   2. Via command line: ./install_module.sh"
echo "   3. Manual command: cd /opt/instance1/odoo17 && python3 odoo-bin -d MOG_LIVE_15_08 --stop-after-init -i l10n_th_account_tax_report"
