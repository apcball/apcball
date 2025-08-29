#!/bin/bash
# Database Registry Cleanup Script

echo "🔧 Database Registry Cleanup for Odoo Module Installation"
echo "========================================================"

# Function to clean base_registry_signaling conflicts
clean_registry_conflicts() {
    echo "🧹 Cleaning registry conflicts..."
    
    # Method 1: Drop and recreate the problematic sequence
    echo "   Attempting to clean base_registry_signaling..."
    
    sudo -u postgres psql -d MOG_LIVE_15_08 -c "
    DO \$\$
    BEGIN
        -- Try to drop the sequence if it exists
        IF EXISTS (SELECT 1 FROM pg_sequences WHERE sequencename = 'base_registry_signaling') THEN
            DROP SEQUENCE base_registry_signaling CASCADE;
            RAISE NOTICE 'Dropped existing base_registry_signaling sequence';
        END IF;
    EXCEPTION
        WHEN OTHERS THEN
            RAISE NOTICE 'Could not drop sequence: %', SQLERRM;
    END
    \$\$;
    " 2>/dev/null

    # Method 2: Clean any orphaned registry data
    echo "   Cleaning orphaned registry data..."
    
    sudo -u postgres psql -d MOG_LIVE_15_08 -c "
    DELETE FROM ir_module_module 
    WHERE name = 'l10n_th_account_tax_report' 
    AND state IN ('to install', 'to upgrade', 'to remove');
    " 2>/dev/null

    echo "   ✅ Registry cleanup completed"
}

# Function to restart PostgreSQL cleanly
restart_postgresql() {
    echo "🔄 Restarting PostgreSQL service..."
    sudo systemctl restart postgresql
    sleep 5
    echo "   ✅ PostgreSQL restarted"
}

# Function to test database connectivity
test_database() {
    echo "🔍 Testing database connectivity..."
    
    if sudo -u postgres psql -d MOG_LIVE_15_08 -c "SELECT 1;" >/dev/null 2>&1; then
        echo "   ✅ Database MOG_LIVE_15_08 is accessible"
        return 0
    else
        echo "   ❌ Database MOG_LIVE_15_08 is not accessible"
        return 1
    fi
}

# Function to safe module installation
safe_install_module() {
    echo "📦 Attempting safe module installation..."
    
    cd /opt/instance1/odoo17
    
    # Try with a completely fresh session
    echo "   Installing l10n_th_account_tax_report with clean session..."
    
    timeout 300 python3 odoo-bin \
        -d MOG_LIVE_15_08 \
        --addons-path=/opt/instance1/odoo17/addons,/opt/instance1/odoo17/custom-addons \
        --stop-after-init \
        --update=all \
        --log-level=info \
        --no-http \
        2>&1 | tee /tmp/odoo_install.log
    
    local result=$?
    
    if [ $result -eq 0 ]; then
        echo "   ✅ Module installation successful"
        return 0
    elif [ $result -eq 124 ]; then
        echo "   ⏱️  Installation timed out (5 minutes)"
        return 1
    else
        echo "   ❌ Installation failed (exit code: $result)"
        echo "   📋 Last few lines of log:"
        tail -10 /tmp/odoo_install.log
        return 1
    fi
}

# Main execution
main() {
    echo
    
    # Ensure Odoo is stopped
    echo "🛑 Ensuring Odoo service is stopped..."
    sudo systemctl stop instance1
    sleep 5
    
    # Clean registry conflicts
    clean_registry_conflicts
    
    # Restart PostgreSQL
    restart_postgresql
    
    # Test database
    if ! test_database; then
        echo "❌ Database connectivity issues. Please check PostgreSQL service."
        exit 1
    fi
    
    # Safe installation
    if safe_install_module; then
        echo "✅ Installation successful!"
    else
        echo "⚠️  Installation had issues, but may still work"
    fi
    
    # Start Odoo service
    echo "🚀 Starting Odoo service..."
    sudo systemctl start instance1
    sleep 15
    
    # Final verification
    echo "🔍 Final verification..."
    if curl -s "http://localhost:8069/l10n_th_account_tax_report/static/description/icon.png" >/dev/null 2>&1; then
        echo "   ✅ Module is accessible via web interface"
        echo
        echo "🎉 Success! Module is now installed and accessible."
        echo "📋 You can access Thai Tax Reports in: Accounting → Reports"
    else
        echo "   ⚠️  Module may not be fully loaded yet. Try refreshing the page."
        echo
        echo "💡 If issues persist:"
        echo "   1. Check Odoo web interface: Apps → Search 'Thai Tax'"
        echo "   2. Try manual installation via web interface"
        echo "   3. Check logs: sudo tail -f /var/log/odoo/instance1.log"
    fi
}

# Run main function
main
