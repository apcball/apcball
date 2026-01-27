#!/bin/bash
###############################################################################
# Stock Valuation Location Module - Safe Upgrade Script
# 
# This script safely upgrades the stock_valuation_location module with
# proper backup and recovery procedures.
#
# Usage: ./upgrade_stock_valuation_location.sh [database_name]
###############################################################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
ODOO_PATH="/opt/instance1/odoo17"
ODOO_BIN="${ODOO_PATH}/odoo-bin"
ODOO_CONF="${ODOO_PATH}/odoo.conf"
MODULE_NAME="stock_valuation_location"
BACKUP_DIR="/tmp/odoo_backup_$(date +%Y%m%d_%H%M%S)"

# Get database name
if [ -z "$1" ]; then
    echo -e "${RED}Error: Database name required${NC}"
    echo "Usage: $0 <database_name>"
    exit 1
fi

DB_NAME="$1"

###############################################################################
# Functions
###############################################################################

print_header() {
    echo -e "\n${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}\n"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

check_prerequisites() {
    print_header "Checking Prerequisites"
    
    # Check if running as correct user
    if [ "$(whoami)" != "mogenit" ] && [ "$(whoami)" != "root" ]; then
        print_warning "Should run as 'mogenit' or 'root' user"
    fi
    
    # Check if Odoo binary exists
    if [ ! -f "$ODOO_BIN" ]; then
        print_error "Odoo binary not found at: $ODOO_BIN"
        exit 1
    fi
    print_success "Odoo binary found"
    
    # Check if config exists
    if [ ! -f "$ODOO_CONF" ]; then
        print_error "Odoo config not found at: $ODOO_CONF"
        exit 1
    fi
    print_success "Odoo config found"
    
    # Check if module exists
    MODULE_PATH="${ODOO_PATH}/custom-addons/${MODULE_NAME}"
    if [ ! -d "$MODULE_PATH" ]; then
        print_error "Module not found at: $MODULE_PATH"
        exit 1
    fi
    print_success "Module found at: $MODULE_PATH"
    
    # Check if database exists
    if ! sudo -u postgres psql -lqt | cut -d \| -f 1 | grep -qw "$DB_NAME"; then
        print_error "Database '$DB_NAME' not found"
        exit 1
    fi
    print_success "Database '$DB_NAME' found"
}

backup_database() {
    print_header "Backing Up Database"
    
    mkdir -p "$BACKUP_DIR"
    BACKUP_FILE="${BACKUP_DIR}/${DB_NAME}_$(date +%Y%m%d_%H%M%S).dump"
    
    print_info "Creating backup: $BACKUP_FILE"
    sudo -u postgres pg_dump -Fc "$DB_NAME" > "$BACKUP_FILE"
    
    if [ -f "$BACKUP_FILE" ]; then
        BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
        print_success "Backup created successfully (Size: $BACKUP_SIZE)"
        echo "Backup location: $BACKUP_FILE"
    else
        print_error "Backup failed!"
        exit 1
    fi
}

check_module_status() {
    print_header "Checking Module Status"
    
    # Query module state from database
    MODULE_STATE=$(sudo -u postgres psql -d "$DB_NAME" -tAc \
        "SELECT state FROM ir_module_module WHERE name='$MODULE_NAME';" 2>/dev/null || echo "not_found")
    
    if [ "$MODULE_STATE" == "not_found" ] || [ -z "$MODULE_STATE" ]; then
        print_warning "Module not installed yet"
        return 1
    else
        print_info "Current module state: $MODULE_STATE"
        return 0
    fi
}

stop_odoo_service() {
    print_header "Stopping Odoo Service"
    
    if systemctl is-active --quiet odoo17; then
        print_info "Stopping Odoo service..."
        sudo systemctl stop odoo17
        sleep 2
        print_success "Odoo service stopped"
    else
        print_info "Odoo service is not running"
    fi
}

upgrade_module() {
    print_header "Upgrading Module"
    
    print_info "Running Odoo upgrade command..."
    print_info "This may take several minutes depending on data size..."
    
    # Run upgrade
    cd "$ODOO_PATH"
    python3 "$ODOO_BIN" -c "$ODOO_CONF" -d "$DB_NAME" -u "$MODULE_NAME" --stop-after-init
    
    if [ $? -eq 0 ]; then
        print_success "Module upgrade completed successfully"
    else
        print_error "Module upgrade failed!"
        print_warning "Check the logs for details"
        exit 1
    fi
}

start_odoo_service() {
    print_header "Starting Odoo Service"
    
    print_info "Starting Odoo service..."
    sudo systemctl start odoo17
    sleep 3
    
    if systemctl is-active --quiet odoo17; then
        print_success "Odoo service started successfully"
    else
        print_error "Failed to start Odoo service"
        print_warning "Check service status with: systemctl status odoo17"
        exit 1
    fi
}

verify_upgrade() {
    print_header "Verifying Upgrade"
    
    # Wait a bit for Odoo to fully start
    print_info "Waiting for Odoo to fully initialize..."
    sleep 5
    
    # Check module version
    NEW_VERSION=$(sudo -u postgres psql -d "$DB_NAME" -tAc \
        "SELECT latest_version FROM ir_module_module WHERE name='$MODULE_NAME';" 2>/dev/null)
    
    if [ ! -z "$NEW_VERSION" ]; then
        print_success "Module version: $NEW_VERSION"
    fi
    
    # Check if compute field was added
    FIELD_EXISTS=$(sudo -u postgres psql -d "$DB_NAME" -tAc \
        "SELECT COUNT(*) FROM ir_model_fields WHERE name='location_id' AND model='stock.valuation.layer';" 2>/dev/null)
    
    if [ "$FIELD_EXISTS" -gt "0" ]; then
        print_success "location_id field exists"
    else
        print_warning "location_id field not found"
    fi
    
    # Count SVL records
    SVL_COUNT=$(sudo -u postgres psql -d "$DB_NAME" -tAc \
        "SELECT COUNT(*) FROM stock_valuation_layer;" 2>/dev/null)
    
    if [ ! -z "$SVL_COUNT" ]; then
        print_info "Total SVL records: $SVL_COUNT"
    fi
}

print_next_steps() {
    print_header "Next Steps"
    
    echo -e "${GREEN}Module upgrade completed successfully!${NC}\n"
    echo "📋 Recommended next steps:"
    echo ""
    echo "1. Test the module functionality:"
    echo "   - Go to Inventory → Reporting → Stock Valuation"
    echo "   - Check if 'Location' column appears"
    echo ""
    echo "2. Run initial recompute (choose one method):"
    echo ""
    echo "   Method A - ORM Recompute (Safe, for < 100k records):"
    echo "   - Go to Inventory → Configuration → Recompute SVL Location (ORM)"
    echo ""
    echo "   Method B - SQL Fast Path (For large databases):"
    echo "   - Go to Inventory → Configuration → SVL Location — Fast SQL"
    echo "   - Enable 'Dry run' first to see affected records"
    echo "   - Set Limit to 10000-50000"
    echo "   - Run multiple times until complete"
    echo ""
    echo "3. Monitor the logs:"
    echo "   tail -f /var/log/odoo/odoo-server.log | grep 'SVL location'"
    echo ""
    echo "4. Backup location:"
    echo "   $BACKUP_FILE"
    echo ""
    print_success "For detailed instructions, see: FIX_SUMMARY.md"
}

###############################################################################
# Main Execution
###############################################################################

main() {
    clear
    print_header "Stock Valuation Location Module Upgrade"
    echo "Database: $DB_NAME"
    echo "Module: $MODULE_NAME"
    echo ""
    
    # Confirmation
    read -p "Continue with upgrade? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_info "Upgrade cancelled"
        exit 0
    fi
    
    # Execute upgrade steps
    check_prerequisites
    check_module_status
    backup_database
    stop_odoo_service
    upgrade_module
    start_odoo_service
    verify_upgrade
    print_next_steps
    
    print_header "Upgrade Complete!"
}

# Run main function
main
