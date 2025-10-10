#!/bin/bash
# l10n_th_account_tax_report Installation Test Script for Odoo 17
# Usage: ./test_install_l10n_th_account_tax_report.sh [database_name] [config_file]

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=========================================="
echo "l10n_th_account_tax_report Module Test"
echo "Odoo 17 Compatibility Check"
echo "=========================================="
echo ""

# Configuration
DATABASE=${1:-"odoo17"}
CONFIG_FILE=${2:-"/etc/odoo.conf"}
MODULE_NAME="l10n_th_account_tax_report"
MODULE_PATH="/opt/instance1/odoo17/custom-addons/${MODULE_NAME}"

# Check if module directory exists
if [ ! -d "$MODULE_PATH" ]; then
    echo -e "${RED}ERROR: Module directory not found at ${MODULE_PATH}${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Module directory found${NC}"

# Step 1: Syntax check for Python files
echo ""
echo "Step 1: Checking Python syntax..."
cd "$MODULE_PATH"
SYNTAX_ERRORS=0

while IFS= read -r -d '' file; do
    if ! python3 -m py_compile "$file" 2>/dev/null; then
        echo -e "${RED}  ✗ Syntax error in: $file${NC}"
        SYNTAX_ERRORS=$((SYNTAX_ERRORS + 1))
    fi
done < <(find . -name "*.py" -type f -print0)

if [ $SYNTAX_ERRORS -eq 0 ]; then
    echo -e "${GREEN}✓ All Python files have valid syntax${NC}"
else
    echo -e "${RED}✗ Found $SYNTAX_ERRORS Python file(s) with syntax errors${NC}"
    exit 1
fi

# Step 2: XML validation
echo ""
echo "Step 2: Validating XML files..."
XML_ERRORS=0

while IFS= read -r -d '' file; do
    if ! xmllint --noout "$file" 2>/dev/null; then
        echo -e "${RED}  ✗ XML error in: $file${NC}"
        XML_ERRORS=$((XML_ERRORS + 1))
    fi
done < <(find . -name "*.xml" -type f -print0)

if [ $XML_ERRORS -eq 0 ]; then
    echo -e "${GREEN}✓ All XML files are valid${NC}"
else
    echo -e "${RED}✗ Found $XML_ERRORS XML file(s) with errors${NC}"
    exit 1
fi

# Step 3: Check dependencies
echo ""
echo "Step 3: Checking module dependencies..."
DEPS_PATH="/opt/instance1/odoo17/custom-addons"
REQUIRED_MODULES=("date_range" "report_xlsx_helper" "l10n_th_base_utils" "l10n_th_partner" "l10n_th_account_tax")
MISSING_DEPS=0

for dep in "${REQUIRED_MODULES[@]}"; do
    if [ ! -d "${DEPS_PATH}/${dep}" ]; then
        echo -e "${RED}  ✗ Missing dependency: $dep${NC}"
        MISSING_DEPS=$((MISSING_DEPS + 1))
    else
        echo -e "${GREEN}  ✓ Found: $dep${NC}"
    fi
done

if [ $MISSING_DEPS -gt 0 ]; then
    echo -e "${RED}✗ Missing $MISSING_DEPS required dependency/dependencies${NC}"
    exit 1
fi

# Step 4: Check for Odoo 18 specific code
echo ""
echo "Step 4: Checking for Odoo 18 incompatibilities..."
if grep -r "self\.env\._(" --include="*.py" "$MODULE_PATH" >/dev/null 2>&1; then
    echo -e "${RED}✗ Found Odoo 18 specific code (self.env._)${NC}"
    grep -rn "self\.env\._(" --include="*.py" "$MODULE_PATH"
    exit 1
else
    echo -e "${GREEN}✓ No Odoo 18 specific incompatibilities found${NC}"
fi

# Summary
echo ""
echo "=========================================="
echo -e "${GREEN}✓ All pre-installation checks passed!${NC}"
echo "=========================================="
echo ""
echo "The module appears to be compatible with Odoo 17."
echo ""
echo "To install the module, run one of these commands:"
echo ""
echo "Method 1 - Through Odoo UI:"
echo "  1. Go to Apps → Update Apps List"
echo "  2. Search for 'Thai Localization - VAT and Withholding Tax Reports'"
echo "  3. Click Install"
echo ""
echo "Method 2 - Command line (requires Odoo configuration):"
echo "  cd /opt/instance1/odoo17"
echo "  ./odoo-bin -c ${CONFIG_FILE} -d ${DATABASE} -i ${MODULE_NAME} --stop-after-init"
echo ""
echo -e "${YELLOW}Note: Make sure all dependency modules are installed first!${NC}"
echo ""
