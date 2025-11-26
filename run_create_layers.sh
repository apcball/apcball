#!/bin/bash
# Quick script to create missing valuation layers

cd /opt/instance1/odoo17

# Temporarily rename problematic test file
if [ -f "/opt/instance1/odoo17/custom-addons/date_range/tests/__init__.py" ]; then
    sudo mv /opt/instance1/odoo17/custom-addons/date_range/tests/__init__.py /opt/instance1/odoo17/custom-addons/date_range/tests/__init__.py.bak 2>/dev/null || true
fi

# Run the script
python3 odoo-bin shell -d MOG_LIVE_15_08 --no-http <<'PYEOF'
exec(open('/opt/instance1/odoo17/custom-addons/create_missing_valuation_layers.py').read())
PYEOF

# Restore test file
if [ -f "/opt/instance1/odoo17/custom-addons/date_range/tests/__init__.py.bak" ]; then
    sudo mv /opt/instance1/odoo17/custom-addons/date_range/tests/__init__.py.bak /opt/instance1/odoo17/custom-addons/date_range/tests/__init__.py 2>/dev/null || true
fi
