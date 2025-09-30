#!/bin/bash
# Diagnostic script to check why l10n_th_account_tax_report installation is failing

echo "=== Diagnosing l10n_th_account_tax_report installation issues ==="

# Check Odoo logs for errors
echo -e "\n1. Checking Odoo logs..."
if [ -f "/var/log/odoo/odoo-server.log" ]; then
    echo "Found Odoo log file at /var/log/odoo/odoo-server.log"
    tail -n 50 /var/log/odoo/odoo-server.log | grep -i "l10n_th_account_tax_report" || echo "No specific errors found in log tail"
elif [ -f "$HOME/odoo-server.log" ]; then
    echo "Found Odoo log file at $HOME/odoo-server.log"
    tail -n 50 $HOME/odoo-server.log | grep -i "l10n_th_account_tax_report" || echo "No specific errors found in log tail"
else
    echo "No standard log file found. Check your Odoo configuration for log file location."
fi

# Check if dependencies are installed
echo -e "\n2. Checking dependencies..."
ODOO_PYTHON=$(which python3)
if [ ! -z "$ODOO_PYTHON" ]; then
    echo "Checking if required Python packages are installed..."
    python3 -c "import xlsxwriter" 2>/dev/null && echo "xlsxwriter ✓" || echo "xlsxwriter ✗"
else
    echo "Python not found"
fi

# Check if dependent modules are installed in Odoo
echo -e "\n3. Checking dependent modules in Odoo database..."
if [ -n "$ODOO_RC" ] || [ -f "/etc/odoo/odoo.conf" ] || [ -f "$HOME/odoo.conf" ]; then
    CONF_FILE=""
    if [ -f "/etc/odoo/odoo.conf" ]; then
        CONF_FILE="/etc/odoo/odoo.conf"
    elif [ -f "$HOME/odoo.conf" ]; then
        CONF_FILE="$HOME/odoo.conf"
    elif [ -n "$ODOO_RC" ]; then
        CONF_FILE="$ODOO_RC"
    fi
    
    if [ -n "$CONF_FILE" ]; then
        echo "Using configuration file: $CONF_FILE"
        DB_NAME=$(grep "^db_name" $CONF_FILE | cut -d'=' -f2 | tr -d ' ')
        DB_HOST=$(grep "^db_host" $CONF_FILE | cut -d'=' -f2 | tr -d ' ')
        DB_USER=$(grep "^db_user" $CONF_FILE | cut -d'=' -f2 | tr -d ' ')
        if [ -z "$DB_NAME" ]; then
            DB_NAME="odoo"
        fi
        if [ -z "$DB_HOST" ]; then
            DB_HOST="localhost"
        fi
        if [ -z "$DB_USER" ]; then
            DB_USER="odoo"
        fi
        DB_PORT=$(grep "^db_port" $CONF_FILE | cut -d'=' -f2 | tr -d ' ' | sed 's/^$/5432/')
        if [ -z "$DB_PORT" ]; then
            DB_PORT="5432"
        fi
        
        # Check if dependent modules are installed
        psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -c "
        SELECT name, state 
        FROM ir_module_module 
        WHERE name IN (
            'l10n_th_base_utils', 
            'l10n_th_partner', 
            'l10n_th_account_tax', 
            'date_range', 
            'report_xlsx_helper',
            'account'
        );
        " 2>/dev/null || echo "Could not connect to database to check modules"
    fi
else
    echo "No Odoo configuration file found. Cannot check installed modules."
fi

# Check module file integrity
echo -e "\n4. Checking module file integrity..."
if [ -d "/opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report" ]; then
    echo "Module directory exists ✓"
    
    # Check key files
    for file in __manifest__.py __init__.py hooks.py; do
        if [ -f "/opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report/$file" ]; then
            echo "$file ✓"
        else
            echo "$file ✗"
        fi
    done
    
    # Check for syntax errors in Python files
    echo -e "\nChecking for Python syntax errors..."
    python3 -m py_compile /opt/instance17/custom-addons/l10n_th_account_tax_report/__init__.py 2>&1 || echo "Syntax error in __init__.py"
    python3 -m py_compile /opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report/hooks.py 2>&1 || echo "Syntax error in hooks.py"
else
    echo "Module directory does not exist ✗"
fi

# Check permissions
echo -e "\n5. Checking file permissions..."
ls -la /opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report/ | head -10

echo -e "\n=== Diagnostic complete ==="
echo "If installation is still failing, please run Odoo with --log-level=debug to see detailed error messages."