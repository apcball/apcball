#!/bin/bash
# Safe module installation and diagnostic script

echo "🔍 Thai Tax Report Module - Diagnostic & Fix Tool"
echo "=================================================="

# Function to check Odoo service status
check_odoo_service() {
    if systemctl is-active --quiet instance1; then
        echo "✅ Odoo service is running"
        return 0
    else
        echo "❌ Odoo service is not running"
        return 1
    fi
}

# Function to check database connectivity
check_database() {
    local db_name="$1"
    if sudo -u postgres psql -d "$db_name" -c "SELECT 1;" >/dev/null 2>&1; then
        echo "✅ Database '$db_name' is accessible"
        return 0
    else
        echo "❌ Database '$db_name' is not accessible"
        return 1
    fi
}

# Function to check module dependencies
check_dependencies() {
    echo "📋 Checking module dependencies..."
    
    local deps=("l10n_th_base_utils" "l10n_th_partner" "l10n_th_account_tax" "date_range" "report_xlsx_helper")
    local missing=()
    
    for dep in "${deps[@]}"; do
        if [ -d "/opt/instance1/odoo17/custom-addons/$dep" ]; then
            echo "  ✅ $dep - Available"
        else
            echo "  ❌ $dep - Missing"
            missing+=("$dep")
        fi
    done
    
    if [ ${#missing[@]} -eq 0 ]; then
        echo "✅ All dependencies are available"
        return 0
    else
        echo "❌ Missing dependencies: ${missing[*]}"
        return 1
    fi
}

# Function to check module status via web API
check_module_status() {
    local db_name="$1"
    echo "🔍 Checking module status via database query..."
    
    # Create a temporary Python script to check module status
    cat > /tmp/check_module.py << 'EOF'
import psycopg2
import sys

try:
    conn = psycopg2.connect(
        host="localhost",
        database=sys.argv[1],
        user="odoo",
        password="odoo"
    )
    cur = conn.cursor()
    
    # Check if module exists and its state
    cur.execute("""
        SELECT name, state, latest_version 
        FROM ir_module_module 
        WHERE name = 'l10n_th_account_tax_report'
    """)
    
    result = cur.fetchone()
    if result:
        name, state, version = result
        print(f"Module: {name}")
        print(f"State: {state}")
        print(f"Version: {version}")
        
        if state == 'installed':
            print("✅ Module is properly installed")
        elif state == 'to install':
            print("⏳ Module is queued for installation")
        elif state == 'to upgrade':
            print("🔄 Module needs upgrade")
        elif state == 'uninstalled':
            print("❌ Module is uninstalled")
        else:
            print(f"⚠️  Module state: {state}")
    else:
        print("❌ Module not found in database")
        
    conn.close()
    
except psycopg2.Error as e:
    print(f"❌ Database error: {e}")
except Exception as e:
    print(f"❌ Error: {e}")
EOF

    python3 /tmp/check_module.py "$db_name"
    rm -f /tmp/check_module.py
}

# Function to fix module issues
fix_module_issues() {
    echo "🔧 Attempting to fix module issues..."
    
    # Fix 1: Update module list
    echo "1. Updating module list..."
    cd /opt/instance1/odoo17
    timeout 60 python3 odoo-bin -d MOG_LIVE_15_08 \
        --addons-path=/opt/instance1/odoo17/addons,/opt/instance1/odoo17/custom-addons \
        --stop-after-init -u base --log-level=error >/dev/null 2>&1
    
    if [ $? -eq 0 ]; then
        echo "  ✅ Module list updated"
    else
        echo "  ⚠️  Module list update had issues (this is often normal)"
    fi
    
    # Fix 2: Install dependencies first
    echo "2. Installing dependencies..."
    local deps=("date_range" "l10n_th_base_utils" "l10n_th_partner" "l10n_th_account_tax")
    
    for dep in "${deps[@]}"; do
        echo "   Installing $dep..."
        timeout 120 python3 odoo-bin -d MOG_LIVE_15_08 \
            --addons-path=/opt/instance1/odoo17/addons,/opt/instance1/odoo17/custom-addons \
            --stop-after-init -i "$dep" --log-level=error >/dev/null 2>&1
        
        if [ $? -eq 0 ]; then
            echo "   ✅ $dep installed"
        else
            echo "   ⚠️  $dep installation had issues"
        fi
    done
    
    # Fix 3: Install target module
    echo "3. Installing l10n_th_account_tax_report..."
    timeout 180 python3 odoo-bin -d MOG_LIVE_15_08 \
        --addons-path=/opt/instance1/odoo17/addons,/opt/instance1/odoo17/custom-addons \
        --stop-after-init -i l10n_th_account_tax_report --log-level=error >/dev/null 2>&1
    
    if [ $? -eq 0 ]; then
        echo "   ✅ l10n_th_account_tax_report installed successfully"
        return 0
    elif [ $? -eq 124 ]; then
        echo "   ⏱️  Installation timed out (3 minutes)"
        return 1
    else
        echo "   ❌ Installation failed"
        return 1
    fi
}

# Main execution
main() {
    echo
    echo "🏁 Starting diagnostics..."
    
    # Check Odoo service
    if ! check_odoo_service; then
        echo "Starting Odoo service..."
        sudo systemctl start instance1
        sleep 10
    fi
    
    # Check database
    if ! check_database "MOG_LIVE_15_08"; then
        echo "❌ Cannot access database. Please check PostgreSQL service."
        exit 1
    fi
    
    # Check dependencies
    if ! check_dependencies; then
        echo "❌ Missing dependencies. Please install them first."
        exit 1
    fi
    
    # Check current module status
    check_module_status "MOG_LIVE_15_08"
    
    echo
    read -p "Do you want to attempt automatic fix? (y/N): " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "🔧 Starting automatic fix..."
        if fix_module_issues; then
            echo
            echo "🎉 Fix completed successfully!"
            echo "📋 Final status check:"
            check_module_status "MOG_LIVE_15_08"
        else
            echo
            echo "⚠️  Automatic fix encountered issues."
            echo "💡 Recommendations:"
            echo "   1. Try installing via Odoo web interface (Apps menu)"
            echo "   2. Check Odoo logs: sudo tail -f /var/log/odoo/instance1.log"
            echo "   3. Restart Odoo service: sudo systemctl restart instance1"
        fi
    else
        echo "Manual intervention required."
    fi
    
    echo
    echo "🏁 Diagnostic complete."
}

# Run main function
main
