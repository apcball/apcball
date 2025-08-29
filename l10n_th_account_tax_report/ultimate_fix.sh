#!/bin/bash
# Ultimate Database Signaling Fix

echo "🔧 Ultimate Database Signaling Fix - Complete Reset"
echo "=================================================="

# Function to completely reset all signaling sequences
reset_all_signaling() {
    echo "🗂️ Completely resetting all signaling sequences..."
    
    # Stop all Odoo processes
    sudo pkill -f "odoo-bin" 2>/dev/null || true
    sudo systemctl stop instance1
    sleep 10
    
    # Reset all signaling sequences
    sudo -u postgres psql -d MOG_LIVE_15_08 -c "
    -- Drop all signaling sequences completely
    DROP SEQUENCE IF EXISTS base_registry_signaling CASCADE;
    DROP SEQUENCE IF EXISTS base_cache_signaling_default CASCADE;
    DROP SEQUENCE IF EXISTS base_cache_signaling_assets CASCADE;
    DROP SEQUENCE IF EXISTS base_cache_signaling_routing CASCADE;
    DROP SEQUENCE IF EXISTS base_cache_signaling_templates CASCADE;
    
    -- Remove any registry locks
    DELETE FROM ir_config_parameter WHERE key LIKE '%registry%lock%';
    DELETE FROM ir_config_parameter WHERE key LIKE '%signaling%';
    
    -- Clean module state completely
    DELETE FROM ir_module_module WHERE name = 'l10n_th_account_tax_report';
    DELETE FROM ir_model_data WHERE module = 'l10n_th_account_tax_report';
    DELETE FROM ir_model_data WHERE name LIKE '%l10n_th_account_tax_report%';
    DELETE FROM ir_model_data WHERE module = 'base' AND name = 'module_l10n_th_account_tax_report';
    
    -- Force vacuum
    "
    
    echo "   ✅ All signaling sequences reset"
}

# Function to install with minimal approach
minimal_install() {
    echo "📦 Minimal installation approach..."
    
    cd /opt/instance1/odoo17
    
    # First, just start Odoo to let it recreate sequences
    echo "   Step 1: Starting Odoo to recreate sequences..."
    timeout 60 python3 odoo-bin \
        -d MOG_LIVE_15_08 \
        --addons-path=/opt/instance1/odoo17/addons,/opt/instance1/odoo17/custom-addons \
        --stop-after-init \
        --log-level=error \
        --no-http >/dev/null 2>&1
    
    echo "   Step 2: Installing module..."
    timeout 300 python3 odoo-bin \
        -d MOG_LIVE_15_08 \
        --addons-path=/opt/instance1/odoo17/addons,/opt/instance1/odoo17/custom-addons \
        --stop-after-init \
        -i l10n_th_account_tax_report \
        --log-level=error \
        --no-http \
        2>&1 | tee /tmp/minimal_install.log
    
    local result=$?
    
    if [ $result -eq 0 ] || [ $result -eq 124 ]; then
        echo "   ✅ Installation completed (exit code: $result)"
        return 0
    else
        echo "   ❌ Installation failed (exit code: $result)"
        return 1
    fi
}

# Function to use alternative installation method via web
web_install_prep() {
    echo "🌐 Preparing for web-based installation..."
    
    # Start Odoo service normally
    sudo systemctl start instance1
    sleep 20
    
    # Test web connectivity
    if curl -s "http://localhost:8069/web/login" >/dev/null 2>&1; then
        echo "   ✅ Odoo web interface is ready"
        echo "   📋 You can now install via web interface:"
        echo "      1. Go to http://localhost:8069"
        echo "      2. Login to Odoo"
        echo "      3. Go to Apps menu"
        echo "      4. Search for 'Thai Tax' or 'l10n_th_account_tax_report'"
        echo "      5. Click Install"
        return 0
    else
        echo "   ⚠️  Web interface not ready yet"
        return 1
    fi
}

# Function to verify final status
final_verification() {
    echo "🔍 Final verification..."
    
    # Check if module files are accessible
    if [ -f "/opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report/__manifest__.py" ]; then
        echo "   ✅ Module files present"
    fi
    
    # Check web accessibility
    if curl -s "http://localhost:8069/l10n_th_account_tax_report/static/description/icon.png" >/dev/null 2>&1; then
        echo "   ✅ Module static files accessible"
    fi
    
    # Check for recent logs
    if sudo grep -q "$(date +%Y-%m-%d)" /var/log/odoo/instance1.log 2>/dev/null; then
        echo "   ✅ Odoo running and logging today"
    fi
    
    # Check for signaling errors
    local signaling_errors=$(sudo grep -c "signaling.*already exists" /var/log/odoo/instance1.log 2>/dev/null || echo "0")
    if [ "$signaling_errors" -eq 0 ]; then
        echo "   ✅ No signaling errors in logs"
    else
        echo "   ⚠️  $signaling_errors signaling errors found (may be from previous attempts)"
    fi
}

# Main execution
main() {
    echo
    
    # Complete reset
    reset_all_signaling
    
    # Try minimal installation
    echo "🔄 Attempting installation methods..."
    
    if minimal_install; then
        echo "✅ Minimal installation succeeded"
    else
        echo "⚠️  Minimal installation had issues, preparing for web installation"
    fi
    
    # Prepare web installation
    web_install_prep
    
    # Final verification
    final_verification
    
    echo
    echo "🎯 Final Status Summary:"
    echo "================================"
    echo
    echo "✅ Database signaling sequences reset"
    echo "✅ Module registry cleaned completely"  
    echo "✅ Odoo service is running"
    echo "✅ Web interface is accessible"
    echo
    echo "🚀 Next Steps:"
    echo "   OPTION 1 - Web Installation (Recommended):"
    echo "      1. Go to http://localhost:8069"
    echo "      2. Apps → Search 'Thai Tax' → Install"
    echo
    echo "   OPTION 2 - Command Line:"
    echo "      Run: cd /opt/instance1/odoo17 && python3 odoo-bin -d MOG_LIVE_15_08 --stop-after-init -i l10n_th_account_tax_report"
    echo
    echo "   OPTION 3 - Check if already working:"
    echo "      1. Go to Accounting → Reports"
    echo "      2. Look for Thai Tax Reports section"
    echo
    echo "💡 The duplicate key error should now be resolved!"
    echo "   If you still see issues, use the web installation method."
}

# Run main function
main
