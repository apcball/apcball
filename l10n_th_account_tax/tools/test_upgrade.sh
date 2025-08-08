#!/bin/bash

# Test module upgrade script
echo "Testing l10n_th_account_tax module upgrade..."

# Check if Odoo is accessible
if ! command -v odoo-bin &> /dev/null; then
    echo "Warning: odoo-bin not found in PATH. Try with full path."
    ODOO_BIN="/opt/instance1/odoo17/odoo-bin"
else
    ODOO_BIN="odoo-bin"
fi

echo "Using Odoo binary: $ODOO_BIN"

# Note: This is just a template - replace 'your_database' with actual database name
echo ""
echo "To test the module upgrade, run:"
echo "$ODOO_BIN -d YOUR_DATABASE_NAME -u l10n_th_account_tax --stop-after-init"
echo ""
echo "To install fresh:"
echo "$ODOO_BIN -d YOUR_DATABASE_NAME -i l10n_th_account_tax --stop-after-init"
echo ""
echo "The XML view syntax has been fixed for Odoo 17 compatibility."
echo "The 'attrs' attributes have been replaced with 'invisible' attributes."
