#!/bin/bash

# Script to upgrade buz_valuation_regenerate and stock_valuation_layer_usage modules
# to fix compatibility issues

echo "=================================================="
echo "Stock Layer Usage Compatibility Fix - Upgrade"
echo "=================================================="
echo ""

# Check if database name is provided
if [ -z "$1" ]; then
    echo "Error: Database name is required"
    echo "Usage: ./upgrade_stock_layer_modules.sh <database_name>"
    echo ""
    echo "Example:"
    echo "  ./upgrade_stock_layer_modules.sh my_database"
    exit 1
fi

DATABASE=$1
ODOO_PATH="/opt/instance1/odoo17"
CONFIG_FILE="odoo.conf"

echo "Database: $DATABASE"
echo "Odoo Path: $ODOO_PATH"
echo "Config File: $CONFIG_FILE"
echo ""

# Check if Odoo directory exists
if [ ! -d "$ODOO_PATH" ]; then
    echo "Error: Odoo directory not found: $ODOO_PATH"
    exit 1
fi

# Check if config file exists
if [ ! -f "$ODOO_PATH/$CONFIG_FILE" ]; then
    echo "Error: Config file not found: $ODOO_PATH/$CONFIG_FILE"
    exit 1
fi

cd $ODOO_PATH

echo "Step 1: Checking if modules are installed..."
echo ""

# Check module status
MODULES_TO_CHECK="buz_valuation_regenerate stock_valuation_layer_usage"
MODULES_TO_UPGRADE=""

for MODULE in $MODULES_TO_CHECK; do
    # Check if module is installed
    MODULE_STATE=$(psql -d $DATABASE -tAc "SELECT state FROM ir_module_module WHERE name='$MODULE'")
    
    if [ "$MODULE_STATE" == "installed" ]; then
        echo "✓ Module $MODULE is installed"
        MODULES_TO_UPGRADE="$MODULES_TO_UPGRADE$MODULE,"
    elif [ "$MODULE_STATE" == "to upgrade" ]; then
        echo "✓ Module $MODULE is marked for upgrade"
        MODULES_TO_UPGRADE="$MODULES_TO_UPGRADE$MODULE,"
    elif [ -z "$MODULE_STATE" ]; then
        echo "⚠ Module $MODULE is not installed - will skip"
    else
        echo "⚠ Module $MODULE status: $MODULE_STATE"
    fi
done

# Remove trailing comma
MODULES_TO_UPGRADE=${MODULES_TO_UPGRADE%,}

if [ -z "$MODULES_TO_UPGRADE" ]; then
    echo ""
    echo "Error: No modules to upgrade. Please install the modules first."
    exit 1
fi

echo ""
echo "Step 2: Backing up database (optional)..."
echo "Do you want to backup database $DATABASE before upgrade? (y/n)"
read -r BACKUP_CHOICE

if [[ $BACKUP_CHOICE =~ ^[Yy]$ ]]; then
    BACKUP_FILE="${DATABASE}_backup_$(date +%Y%m%d_%H%M%S).sql"
    echo "Creating backup: $BACKUP_FILE"
    pg_dump $DATABASE > $BACKUP_FILE
    
    if [ $? -eq 0 ]; then
        echo "✓ Backup created successfully: $BACKUP_FILE"
    else
        echo "✗ Backup failed!"
        echo "Do you want to continue without backup? (y/n)"
        read -r CONTINUE_CHOICE
        if [[ ! $CONTINUE_CHOICE =~ ^[Yy]$ ]]; then
            echo "Upgrade cancelled."
            exit 1
        fi
    fi
fi

echo ""
echo "Step 3: Upgrading modules..."
echo "Modules to upgrade: $MODULES_TO_UPGRADE"
echo ""

# Upgrade modules
./odoo-bin -c $CONFIG_FILE -d $DATABASE -u $MODULES_TO_UPGRADE --stop-after-init

if [ $? -eq 0 ]; then
    echo ""
    echo "=================================================="
    echo "✓ Modules upgraded successfully!"
    echo "=================================================="
    echo ""
    echo "Next steps:"
    echo "1. Restart Odoo service"
    echo "2. Test the regeneration functionality"
    echo "3. Verify usage tracking is working correctly"
    echo ""
    echo "Testing steps:"
    echo "- Go to Inventory → Valuation → Re-Generate Valuation"
    echo "- Select a product with stock moves"
    echo "- Run 'Compute Plan' (dry run mode)"
    echo "- If no errors, turn off dry run and 'Apply Regeneration'"
    echo "- Check that SVLs are created correctly"
    echo "- Verify usage records are not created during regeneration"
    echo ""
else
    echo ""
    echo "=================================================="
    echo "✗ Upgrade failed!"
    echo "=================================================="
    echo ""
    echo "Please check the error messages above."
    echo "You may need to:"
    echo "1. Check Odoo logs for more details"
    echo "2. Verify database connection"
    echo "3. Check file permissions"
    echo ""
    
    if [ -f "$BACKUP_FILE" ]; then
        echo "You can restore from backup:"
        echo "  dropdb $DATABASE"
        echo "  createdb $DATABASE"
        echo "  psql $DATABASE < $BACKUP_FILE"
        echo ""
    fi
    
    exit 1
fi

echo "Upgrade script completed."
echo ""
