#!/bin/bash

# WHT Module Test Script
# This script helps verify that l10n_th_account_tax module is working correctly

echo "=========================================="
echo "WHT Tax Module Verification Script"
echo "=========================================="

# Check if we're in the right directory
if [ ! -f "__manifest__.py" ]; then
    echo "Error: Please run this script from the l10n_th_account_tax module directory"
    exit 1
fi

echo "✓ Running from module directory"

# Check Python syntax
echo "Checking Python syntax..."
python3 -m py_compile models/*.py 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✓ Python syntax check passed"
else
    echo "✗ Python syntax errors found"
fi

# Check XML syntax
echo "Checking XML syntax..."
xml_errors=0
for xml_file in $(find . -name "*.xml"); do
    xmllint --noout "$xml_file" 2>/dev/null
    if [ $? -ne 0 ]; then
        echo "✗ XML syntax error in: $xml_file"
        xml_errors=$((xml_errors + 1))
    fi
done

if [ $xml_errors -eq 0 ]; then
    echo "✓ XML syntax check passed"
else
    echo "✗ Found $xml_errors XML syntax errors"
fi

# Check manifest structure
echo "Checking manifest structure..."
if python3 -c "import ast; ast.parse(open('__manifest__.py').read())" 2>/dev/null; then
    echo "✓ Manifest syntax is valid"
else
    echo "✗ Manifest syntax error"
fi

# Check required files exist
echo "Checking required files..."
required_files=(
    "models/__init__.py"
    "models/account_withholding_tax.py"
    "models/account_payment.py"
    "wizard/account_payment_register.py"
    "security/ir.model.access.csv"
)

for file in "${required_files[@]}"; do
    if [ -f "$file" ]; then
        echo "✓ $file exists"
    else
        echo "✗ $file missing"
    fi
done

# Check data files
echo "Checking data files..."
if [ -f "data/withholding_tax_type_income_data.xml" ]; then
    echo "✓ WHT income type data exists"
else
    echo "✗ WHT income type data missing"
fi

if [ -f "data/pit_rate_data.xml" ]; then
    echo "✓ PIT rate data exists"
else
    echo "✗ PIT rate data missing"
fi

# Summary
echo "=========================================="
echo "Verification complete!"
echo ""
echo "Next steps if issues found:"
echo "1. Fix any syntax errors shown above"
echo "2. Run: odoo-bin -d your_db -i l10n_th_account_tax --test-enable"
echo "3. Check Odoo logs for runtime errors"
echo "4. Use the WHT Setup Wizard in Odoo"
echo "5. Refer to IMPLEMENTATION_GUIDE.md"
echo "=========================================="
