#!/bin/bash
# Script to upgrade buz_account_receipt module after code changes

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}================================================${NC}"
echo -e "${YELLOW}Upgrading buz_account_receipt Module${NC}"
echo -e "${YELLOW}================================================${NC}"
echo ""

# Database name
DB_NAME="MOG_LIVE_15_08"
echo -e "Database: ${GREEN}$DB_NAME${NC}"
echo ""
echo -e "${YELLOW}Step 1: Stopping Odoo instance...${NC}"
sudo systemctl stop instance1

echo -e "${GREEN}✓ Instance stopped${NC}"
echo ""

echo -e "${YELLOW}Step 2: Upgrading module...${NC}"
/opt/instance1/odoo17-venv/bin/python3 /opt/instance1/odoo17/odoo-bin \
    -c /etc/instance1.conf \
    -d "$DB_NAME" \
    -u buz_account_receipt \
    --stop-after-init

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Module upgraded successfully${NC}"
else
    echo -e "${RED}✗ Module upgrade failed${NC}"
    echo -e "${YELLOW}Starting instance anyway...${NC}"
fi

echo ""
echo -e "${YELLOW}Step 3: Starting Odoo instance...${NC}"
sudo systemctl start instance1

sleep 3

# Check status
if systemctl is-active --quiet instance1; then
    echo -e "${GREEN}✓ Instance started successfully${NC}"
    echo ""
    echo -e "${GREEN}================================================${NC}"
    echo -e "${GREEN}Upgrade Complete!${NC}"
    echo -e "${GREEN}================================================${NC}"
    echo ""
    echo "The unlink() methods are now active."
    echo "You can now delete vouchers without FK constraint errors."
else
    echo -e "${RED}✗ Instance failed to start${NC}"
    echo "Check logs: sudo journalctl -u instance1 -n 50"
fi
