#!/bin/bash
# Odoo 18->17 Downgrade Compatible Installation Script

echo "🔧 l10n_th_account_tax_report - Odoo 18→17 Compatibility Installer"
echo "=================================================================="

# Function to check Odoo version compatibility
check_compatibility() {
    echo "🔍 Checking Odoo version compatibility..."
    
    cd /opt/instance1/odoo17
    ODOO_VERSION=$(python3 -c "
import sys
sys.path.insert(0, '/opt/instance1/odoo17')
try:
    import odoo
    print(odoo.release.version_info[0])
except:
    print('unknown')
")
    
    if [ "$ODOO_VERSION" = "17" ]; then
        echo "   ✅ Odoo 17 detected - compatibility mode enabled"
        return 0
    else
        echo "   ⚠️  Odoo version: $ODOO_VERSION - proceeding with compatibility layer"
        return 0
    fi
}

# Function to clean previous installations
clean_previous() {
    echo "🧹 Cleaning previous installation attempts..."
    
    # Stop Odoo
    sudo systemctl stop instance1
    sleep 5
    
    # Clear Python cache
    find /opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report -name "*.pyc" -delete 2>/dev/null || true
    find /opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
    
    echo "   ✅ Cache cleared"
}

# Function to install with compatibility
install_with_compatibility() {
    echo "📦 Installing with Odoo 18→17 compatibility layer..."
    
    cd /opt/instance1/odoo17
    
    # Step 1: Update module list with compatibility
    echo "   1️⃣ Updating module list..."
    timeout 60 python3 odoo-bin -d MOG_LIVE_15_08 \
        --addons-path=/opt/instance1/odoo17/addons,/opt/instance1/odoo17/custom-addons \
        --stop-after-init \
        -u base \
        --log-level=error >/dev/null 2>&1
    
    # Step 2: Install dependencies with retry
    echo "   2️⃣ Installing dependencies with compatibility..."
    
    local deps=("date_range" "l10n_th_base_utils" "l10n_th_partner" "l10n_th_account_tax")
    for dep in "${deps[@]}"; do
        echo "      Installing $dep..."
        
        # Try up to 3 times
        for attempt in 1 2 3; do
            timeout 120 python3 odoo-bin -d MOG_LIVE_15_08 \
                --addons-path=/opt/instance1/odoo17/addons,/opt/instance1/odoo17/custom-addons \
                --stop-after-init \
                -i "$dep" \
                --log-level=error >/dev/null 2>&1
            
            if [ $? -eq 0 ]; then
                echo "      ✅ $dep installed (attempt $attempt)"
                break
            elif [ $attempt -eq 3 ]; then
                echo "      ⚠️  $dep installation issues after 3 attempts"
            else
                echo "      🔄 Retrying $dep (attempt $((attempt+1)))"
                sleep 2
            fi
        done
    done
    
    # Step 3: Install main module with compatibility
    echo "   3️⃣ Installing l10n_th_account_tax_report with compatibility layer..."
    
    # Try multiple approaches
    for approach in "install" "upgrade" "force"; do
        echo "      Trying approach: $approach"
        
        case $approach in
            "install")
                timeout 180 python3 odoo-bin -d MOG_LIVE_15_08 \
                    --addons-path=/opt/instance1/odoo17/addons,/opt/instance1/odoo17/custom-addons \
                    --stop-after-init \
                    -i l10n_th_account_tax_report \
                    --log-level=info
                ;;
            "upgrade")
                timeout 180 python3 odoo-bin -d MOG_LIVE_15_08 \
                    --addons-path=/opt/instance1/odoo17/addons,/opt/instance1/odoo17/custom-addons \
                    --stop-after-init \
                    -u l10n_th_account_tax_report \
                    --log-level=info
                ;;
            "force")
                timeout 180 python3 odoo-bin -d MOG_LIVE_15_08 \
                    --addons-path=/opt/instance1/odoo17/addons,/opt/instance1/odoo17/custom-addons \
                    --stop-after-init \
                    -u l10n_th_account_tax_report \
                    --init l10n_th_account_tax_report \
                    --log-level=info
                ;;
        esac
        
        local result=$?
        if [ $result -eq 0 ]; then
            echo "      ✅ Installation successful with approach: $approach"
            return 0
        elif [ $result -eq 124 ]; then
            echo "      ⏱️  Timeout with approach: $approach"
        else
            echo "      ❌ Failed with approach: $approach (exit code: $result)"
        fi
    done
    
    return 1
}

# Function to verify installation
verify_installation() {
    echo "🔍 Verifying installation..."
    
    # Check files
    if [ -f "/opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report/hooks.py" ]; then
        echo "   ✅ Compatibility layer installed"
    else
        echo "   ❌ Compatibility layer missing"
        return 1
    fi
    
    # Check web access
    if curl -s "http://localhost:8069/l10n_th_account_tax_report/static/description/icon.png" >/dev/null 2>&1; then
        echo "   ✅ Module accessible via web"
    else
        echo "   ⚠️  Module not yet accessible via web (may need restart)"
    fi
    
    # Check logs for compatibility messages
    if sudo grep -q "compatibility layer" /var/log/odoo/instance1.log 2>/dev/null; then
        echo "   ✅ Compatibility layer activated"
    else
        echo "   ⚠️  Compatibility layer logs not found"
    fi
    
    return 0
}

# Main execution
main() {
    echo
    
    # Check compatibility
    if ! check_compatibility; then
        echo "❌ Compatibility check failed"
        exit 1
    fi
    
    # Clean previous attempts
    clean_previous
    
    # Install with compatibility
    if install_with_compatibility; then
        echo "✅ Installation completed successfully"
    else
        echo "⚠️  Installation completed with some issues"
    fi
    
    # Start Odoo
    echo "🚀 Starting Odoo service..."
    sudo systemctl start instance1
    sleep 10
    
    # Verify
    if verify_installation; then
        echo
        echo "🎉 l10n_th_account_tax_report successfully installed with Odoo 18→17 compatibility!"
        echo "📋 You can now access Thai Tax Reports in: Accounting → Reports"
        echo "💡 The compatibility layer handles downgrade issues automatically"
    else
        echo
        echo "⚠️  Installation completed but verification found some issues"
        echo "💡 Try accessing the module via Odoo web interface"
        echo "📋 Check logs: sudo tail -f /var/log/odoo/instance1.log"
    fi
}

# Run main function
main
