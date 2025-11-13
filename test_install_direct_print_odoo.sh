#!/bin/bash
# direct_print_odoo Installation Test Script for Odoo 17
# Usage: ./test_install_direct_print_odoo.sh [database_name] [config_file]

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=========================================="
echo "direct_print_odoo Module Test"
echo "Odoo 17 Compatibility Check"
echo "=========================================="
echo ""

# Configuration
DATABASE=${1:-"odoo17"}
CONFIG_FILE=${2:-"/etc/odoo.conf"}
MODULE_NAME="direct_print_odoo"
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

# Step 2: Check XML files for basic syntax
echo ""
echo "Step 2: Checking XML syntax..."
XML_ERRORS=0

while IFS= read -r -d '' file; do
    if ! xmllint --noout "$file" 2>/dev/null; then
        echo -e "${RED}  ✗ XML syntax error in: $file${NC}"
        XML_ERRORS=$((XML_ERRORS + 1))
    fi
done < <(find . -name "*.xml" -type f -print0)

if [ $XML_ERRORS -eq 0 ]; then
    echo -e "${GREEN}✓ All XML files have valid syntax${NC}"
else
    echo -e "${RED}✗ Found $XML_ERRORS XML file(s) with syntax errors${NC}"
    exit 1
fi

# Step 3: Check for required dependencies
echo ""
echo "Step 3: Checking Python dependencies..."
MISSING_DEPS=0

# Activate virtual environment
source /opt/instance1/odoo17-venv/bin/activate

# Check printnodeapi
if ! python3 -c "import printnodeapi" 2>/dev/null; then
    echo -e "${RED}  ✗ Missing dependency: printnodeapi${NC}"
    MISSING_DEPS=$((MISSING_DEPS + 1))
else
    echo -e "${GREEN}✓ printnodeapi is available${NC}"
fi

if [ $MISSING_DEPS -eq 0 ]; then
    echo -e "${GREEN}✓ All Python dependencies are satisfied${NC}"
else
    echo -e "${RED}✗ Missing $MISSING_DEPS Python dependencies${NC}"
    exit 1
fi

# Step 4: Check manifest file
echo ""
echo "Step 4: Validating manifest file..."
if [ -f "__manifest__.py" ]; then
    if python3 -c "import ast; ast.parse(open('__manifest__.py').read())" 2>/dev/null; then
        echo -e "${GREEN}✓ Manifest file is valid Python${NC}"
    else
        echo -e "${RED}✗ Manifest file has syntax errors${NC}"
        exit 1
    fi
else
    echo -e "${RED}✗ Manifest file (__manifest__.py) not found${NC}"
    exit 1
fi

# Step 5: Check for required Odoo dependencies
echo ""
echo "Step 5: Checking Odoo module dependencies..."
MANIFEST_DEPS=$(python3 -c "
import ast
with open('__manifest__.py', 'r') as f:
    tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Str) and key.s == 'depends':
                    if isinstance(value, ast.List):
                        deps = [elt.s for elt in value.elts if isinstance(elt, ast.Str)]
                        print(' '.join(deps))
                        break
")

echo "Module depends on: $MANIFEST_DEPS"

# Basic check - ensure base_setup is available (common dependency)
if echo "$MANIFEST_DEPS" | grep -q "base_setup"; then
    echo -e "${GREEN}✓ base_setup dependency found${NC}"
else
    echo -e "${YELLOW}⚠ base_setup dependency not explicitly listed (may be implicit)${NC}"
fi

echo ""
echo "=========================================="
echo -e "${GREEN}✅ Pre-installation checks passed!${NC}"
echo "=========================================="
echo ""
echo "To install the module, run:"
echo "  ./install_direct_print_odoo.sh"
echo ""
echo "Or manually:"
echo "  sudo systemctl stop instance1"
echo "  cd /opt/instance1/odoo17"
echo "  source /opt/instance1/odoo17-venv/bin/activate"
echo "  python3 odoo-bin -c /etc/instance1.conf -d MOG_LIVE_15_08 -i direct_print_odoo --stop-after-init"
echo "  sudo systemctl start instance1"