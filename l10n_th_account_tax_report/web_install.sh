#!/bin/bash
# Web-based Module Installation

echo "🌐 Installing Thai Tax Report Module via Web Interface"
echo "===================================================="

# Function to install module via web API
install_via_web() {
    echo "📦 Installing module via Odoo web API..."
    
    # Get session cookie
    COOKIE=$(curl -s -c /tmp/odoo_cookie -b /tmp/odoo_cookie \
        -X POST "http://localhost:8069/web/session/authenticate" \
        -H "Content-Type: application/json" \
        -d '{"jsonrpc":"2.0","method":"call","params":{"db":"MOG_LIVE_15_08","login":"admin","password":"admin"},"id":1}' \
        | grep -o '"session_id":"[^"]*"' | cut -d'"' -f4)
    
    if [ -n "$COOKIE" ]; then
        echo "   ✅ Session established"
        
        # Update module list first
        curl -s -b /tmp/odoo_cookie \
            -X POST "http://localhost:8069/web/dataset/call_kw" \
            -H "Content-Type: application/json" \
            -d '{"jsonrpc":"2.0","method":"call","params":{"model":"ir.module.module","method":"update_list","args":[],"kwargs":{}},"id":2}' \
            >/dev/null
        
        echo "   ✅ Module list updated"
        
        # Install the module
        RESULT=$(curl -s -b /tmp/odoo_cookie \
            -X POST "http://localhost:8069/web/dataset/call_kw" \
            -H "Content-Type: application/json" \
            -d '{"jsonrpc":"2.0","method":"call","params":{"model":"ir.module.module","method":"button_immediate_install","args":[],"kwargs":{"context":{"install_mode":true,"module_name":"l10n_th_account_tax_report"}}},"id":3}')
        
        if echo "$RESULT" | grep -q '"result"'; then
            echo "   ✅ Module installation initiated"
            return 0
        else
            echo "   ⚠️  Installation failed via web API"
            return 1
        fi
    else
        echo "   ❌ Could not establish session"
        return 1
    fi
}

# Main execution
echo
if install_via_web; then
    echo
    echo "🎯 Installation Complete!"
    echo "======================="
    echo
    echo "📍 Access Thai Tax Reports:"
    echo "   1. Login to: http://localhost:8069"
    echo "   2. Go to: Accounting → Reports"
    echo "   3. Look for Thai tax report options"
    echo
else
    echo
    echo "⚠️  Web installation failed"
    echo "========================="
    echo
    echo "💡 Manual installation steps:"
    echo "   1. Login to Odoo web interface"
    echo "   2. Go to Apps"
    echo "   3. Search for 'l10n_th_account_tax_report'"
    echo "   4. Click Install"
fi

# Cleanup
rm -f /tmp/odoo_cookie 2>/dev/null
