#!/bin/bash
# Installation/Upgrade script for Stock By Location module - Odoo 17

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration - UPDATE THESE
DATABASE="${1:-odoo17}"
ODOO_BIN="${ODOO_BIN:-/opt/instance1/odoo17/odoo-bin}"
ODOO_CONF="${ODOO_CONF:-/etc/odoo17.conf}"
MODULE_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="${BACKUP_DIR:-/tmp/odoo_backups}"

echo -e "${GREEN}=== Stock By Location - Odoo 17 Installation ===${NC}"
echo "Module Path: $MODULE_PATH"
echo "Database: $DATABASE"
echo "Odoo Binary: $ODOO_BIN"
echo "Odoo Config: $ODOO_CONF"
echo ""

# Check if running as correct user
if [ "$EUID" -eq 0 ]; then 
   echo -e "${YELLOW}Warning: Running as root. Consider running as odoo user.${NC}"
fi

# Check if database exists
if ! psql -lqt | cut -d \| -f 1 | grep -qw "$DATABASE"; then
    echo -e "${RED}Error: Database '$DATABASE' does not exist${NC}"
    echo "Usage: $0 <database_name>"
    exit 1
fi

# Check if Odoo binary exists
if [ ! -f "$ODOO_BIN" ]; then
    echo -e "${RED}Error: Odoo binary not found at $ODOO_BIN${NC}"
    echo "Set ODOO_BIN environment variable to correct path"
    exit 1
fi

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Backup database
echo -e "${YELLOW}Creating database backup...${NC}"
BACKUP_FILE="$BACKUP_DIR/stock_by_locations_${DATABASE}_$(date +%Y%m%d_%H%M%S).sql"
if pg_dump "$DATABASE" > "$BACKUP_FILE"; then
    echo -e "${GREEN}✓ Backup created: $BACKUP_FILE${NC}"
else
    echo -e "${RED}✗ Backup failed!${NC}"
    exit 1
fi

# Check module files
echo -e "${YELLOW}Checking module files...${NC}"
required_files=(
    "__init__.py"
    "__manifest__.py"
    "models/__init__.py"
    "views/product_view.xml"
    "security/ir.model.access.csv"
)

for file in "${required_files[@]}"; do
    if [ ! -f "$MODULE_PATH/$file" ]; then
        echo -e "${RED}✗ Missing file: $file${NC}"
        exit 1
    fi
done
echo -e "${GREEN}✓ All required files present${NC}"

# Check dependencies
echo -e "${YELLOW}Checking dependencies...${NC}"
python3 << EOF
import sys
sys.path.insert(0, '$(dirname $ODOO_BIN)')
try:
    import odoo
    from odoo import api, SUPERUSER_ID
    print("${GREEN}✓ Odoo Python modules accessible${NC}")
except ImportError as e:
    print("${RED}✗ Cannot import Odoo: ${NC}" + str(e))
    sys.exit(1)
EOF

# Verify Odoo version
echo -e "${YELLOW}Checking Odoo version...${NC}"
ODOO_VERSION=$(python3 << EOF
import sys
sys.path.insert(0, '$(dirname $ODOO_BIN)')
import odoo
print(odoo.release.version_info[0])
EOF
)

if [ "$ODOO_VERSION" != "17" ]; then
    echo -e "${RED}✗ Wrong Odoo version: $ODOO_VERSION (expected 17)${NC}"
    echo -e "${YELLOW}Continue anyway? (y/N)${NC}"
    read -r response
    if [[ ! "$response" =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo -e "${GREEN}✓ Odoo 17 detected${NC}"
fi

# Check if module is already installed
echo -e "${YELLOW}Checking module status...${NC}"
MODULE_STATE=$(python3 << EOF
import sys
sys.path.insert(0, '$(dirname $ODOO_BIN)')
import odoo
from odoo import api, SUPERUSER_ID
from odoo.tools import config

config.parse_config(['--config=$ODOO_CONF', '--database=$DATABASE'])
with odoo.api.Environment.manage():
    registry = odoo.registry('$DATABASE')
    with registry.cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})
        module = env['ir.module.module'].search([('name', '=', 'stock_by_locations')], limit=1)
        if module:
            print(module.state)
        else:
            print('not_found')
EOF
)

echo "Module state: $MODULE_STATE"

# Determine action
if [ "$MODULE_STATE" == "not_found" ] || [ "$MODULE_STATE" == "uninstalled" ]; then
    ACTION="install"
    echo -e "${GREEN}Will perform fresh installation${NC}"
else
    ACTION="upgrade"
    echo -e "${GREEN}Will perform upgrade${NC}"
fi

# Stop Odoo service if running
echo -e "${YELLOW}Checking Odoo service...${NC}"
if systemctl is-active --quiet odoo17 2>/dev/null; then
    echo -e "${YELLOW}Stopping Odoo service...${NC}"
    sudo systemctl stop odoo17
    RESTART_SERVICE=1
elif systemctl is-active --quiet odoo 2>/dev/null; then
    echo -e "${YELLOW}Stopping Odoo service...${NC}"
    sudo systemctl stop odoo
    RESTART_SERVICE=1
else
    echo "Odoo service not running"
    RESTART_SERVICE=0
fi

# Update/Install module
echo -e "${YELLOW}${ACTION^}ing module...${NC}"
if [ "$ACTION" == "install" ]; then
    CMD="$ODOO_BIN -c $ODOO_CONF -d $DATABASE -i stock_by_locations --stop-after-init --log-level=warn"
else
    CMD="$ODOO_BIN -c $ODOO_CONF -d $DATABASE -u stock_by_locations --stop-after-init --log-level=warn"
fi

echo "Running: $CMD"
if $CMD 2>&1 | tee /tmp/stock_by_locations_install.log; then
    if grep -q "ERROR\|CRITICAL" /tmp/stock_by_locations_install.log; then
        echo -e "${RED}✗ Installation completed with errors. Check /tmp/stock_by_locations_install.log${NC}"
        ERROR=1
    else
        echo -e "${GREEN}✓ Module ${ACTION}ed successfully${NC}"
        ERROR=0
    fi
else
    echo -e "${RED}✗ Installation failed!${NC}"
    ERROR=1
fi

# Restart service if it was running
if [ $RESTART_SERVICE -eq 1 ]; then
    echo -e "${YELLOW}Restarting Odoo service...${NC}"
    if systemctl is-enabled --quiet odoo17 2>/dev/null; then
        sudo systemctl start odoo17
    elif systemctl is-enabled --quiet odoo 2>/dev/null; then
        sudo systemctl start odoo
    fi
    sleep 3
    if systemctl is-active --quiet odoo17 2>/dev/null || systemctl is-active --quiet odoo 2>/dev/null; then
        echo -e "${GREEN}✓ Odoo service restarted${NC}"
    else
        echo -e "${RED}✗ Failed to restart Odoo service${NC}"
        ERROR=1
    fi
fi

# Verify installation
if [ $ERROR -eq 0 ]; then
    echo -e "${YELLOW}Verifying installation...${NC}"
    VERIFY_STATE=$(python3 << EOF
import sys
sys.path.insert(0, '$(dirname $ODOO_BIN)')
import odoo
from odoo import api, SUPERUSER_ID
from odoo.tools import config

config.parse_config(['--config=$ODOO_CONF', '--database=$DATABASE'])
with odoo.api.Environment.manage():
    registry = odoo.registry('$DATABASE')
    with registry.cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})
        module = env['ir.module.module'].search([('name', '=', 'stock_by_locations')], limit=1)
        print(module.state if module else 'not_found')
EOF
)
    
    if [ "$VERIFY_STATE" == "installed" ]; then
        echo -e "${GREEN}✓ Module successfully installed and verified${NC}"
    else
        echo -e "${RED}✗ Module state: $VERIFY_STATE${NC}"
        ERROR=1
    fi
fi

# Summary
echo ""
echo -e "${GREEN}=== Installation Summary ===${NC}"
echo "Action: ${ACTION^}"
echo "Database: $DATABASE"
echo "Backup: $BACKUP_FILE"
echo "Module Path: $MODULE_PATH"
if [ $ERROR -eq 0 ]; then
    echo -e "Status: ${GREEN}SUCCESS${NC}"
    echo ""
    echo "Next steps:"
    echo "1. Log into Odoo"
    echo "2. Go to Inventory > Configuration > Warehouses"
    echo "3. Mark your main warehouse"
    echo "4. Configure product categories to use 'AVCO by Location'"
    echo "5. Configure locations (Exclude from cost, Apply in sale)"
    echo ""
    echo "Documentation:"
    echo "- README.md: Complete module documentation"
    echo "- UPGRADE_TO_ODOO17.md: Upgrade guide and troubleshooting"
else
    echo -e "Status: ${RED}FAILED${NC}"
    echo ""
    echo "Troubleshooting:"
    echo "1. Check installation log: /tmp/stock_by_locations_install.log"
    echo "2. Check Odoo log: tail -f /var/log/odoo/odoo17.log"
    echo "3. Restore backup if needed: psql $DATABASE < $BACKUP_FILE"
    echo "4. Review UPGRADE_TO_ODOO17.md for known issues"
fi

exit $ERROR
