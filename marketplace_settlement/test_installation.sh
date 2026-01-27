#!/bin/bash

# Quick test script for marketplace_settlement module

echo "🔍 Testing Marketplace Settlement Module..."

# Test 1: Check if module directory exists
if [ -d "/opt/instance1/odoo17/custom-addons/marketplace_settlement" ]; then
    echo "✅ Module directory exists"
else
    echo "❌ Module directory not found"
    exit 1
fi

# Test 2: Check essential files
FILES=(
    "__manifest__.py"
    "models/__init__.py"
    "models/settlement.py"
    "models/sale_account_extension.py"
    "wizards/__init__.py"
    "wizards/bill_link_wizard.py"
    "wizards/settlement_preview_wizard.py"
    "views/account_move_view_inherit.xml"
    "views/bill_link_wizard_views.xml"
    "views/settlement_preview_wizard_views.xml"
)

for file in "${FILES[@]}"; do
    if [ -f "/opt/instance1/odoo17/custom-addons/marketplace_settlement/$file" ]; then
        echo "✅ $file exists"
    else
        echo "❌ $file missing"
    fi
done

# Test 3: Check Python syntax
echo "🐍 Checking Python syntax..."
cd /opt/instance1/odoo17/custom-addons/marketplace_settlement

python3 -m py_compile models/settlement.py
if [ $? -eq 0 ]; then
    echo "✅ settlement.py syntax OK"
else
    echo "❌ settlement.py syntax error"
fi

python3 -m py_compile models/sale_account_extension.py
if [ $? -eq 0 ]; then
    echo "✅ sale_account_extension.py syntax OK"
else
    echo "❌ sale_account_extension.py syntax error"
fi

python3 -m py_compile wizards/bill_link_wizard.py
if [ $? -eq 0 ]; then
    echo "✅ bill_link_wizard.py syntax OK"
else
    echo "❌ bill_link_wizard.py syntax error"
fi

# Test 4: Check XML syntax
echo "📄 Checking XML syntax..."
xmllint --noout views/account_move_view_inherit.xml 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✅ account_move_view_inherit.xml syntax OK"
else
    echo "❌ account_move_view_inherit.xml syntax error"
fi

xmllint --noout views/bill_link_wizard_views.xml 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✅ bill_link_wizard_views.xml syntax OK"
else
    echo "❌ bill_link_wizard_views.xml syntax error"
fi

# Test 5: Check if Odoo is running
if pgrep -f "odoo-bin" > /dev/null; then
    echo "✅ Odoo is running"
else
    echo "⚠️  Odoo is not running"
fi

echo "🎯 Module test completed!"
echo ""
echo "📋 Next steps:"
echo "1. Go to Odoo Apps"
echo "2. Update app list"
echo "3. Search for 'Marketplace Settlement'"
echo "4. Upgrade the module"
echo "5. Test the new features:"
echo "   - Create vendor bills"
echo "   - Link bills to settlements"
echo "   - Preview AR/AP netting"
echo "   - Perform netting"
