#!/bin/bash
# Installation script for l10n_th_account_tax_report module

echo "🚀 Starting l10n_th_account_tax_report installation..."

# Check if Odoo is running
if pgrep -f "odoo-bin" > /dev/null; then
    echo "⚠️  Odoo is currently running. For best results, consider stopping it first."
    echo "   You can continue, but installation might be slower."
    read -p "Continue anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Installation cancelled."
        exit 1
    fi
fi

# Test dependencies
echo "📋 Checking dependencies..."
cd /opt/instance1/odoo17/custom-addons/l10n_th_account_tax_report
python3 test_dependencies.py

if [ $? -ne 0 ]; then
    echo "❌ Dependency check failed. Please fix dependencies first."
    exit 1
fi

# Create a simple database update command
echo "📦 Preparing installation..."

# Get available databases
echo "Available databases:"
sudo -u postgres psql -l | grep -E "^\s+\w+\s+\|\s+odoo\s+\|" | awk '{print "  - " $1}'

echo
read -p "Enter database name for installation (or press Enter for MOG_LIVE_15_08): " DB_NAME
DB_NAME=${DB_NAME:-MOG_LIVE_15_08}

echo "🔧 Installing module in database: $DB_NAME"

# Create installation command with timeout
INSTALL_CMD="cd /opt/instance1/odoo17 && timeout 300 python3 odoo-bin \\
  --addons-path=/opt/instance1/odoo17/addons,/opt/instance1/odoo17/custom-addons \\
  -d $DB_NAME \\
  --stop-after-init \\
  -i l10n_th_account_tax_report \\
  --log-level=info \\
  --no-http"

echo "Running: $INSTALL_CMD"
echo "⏱️  Installation will timeout after 5 minutes if it hangs..."

eval $INSTALL_CMD

RESULT=$?

if [ $RESULT -eq 0 ]; then
    echo "✅ Module installed successfully!"
elif [ $RESULT -eq 124 ]; then
    echo "⏱️  Installation timed out. This might indicate a performance issue."
    echo "   You can try:"
    echo "   1. Installing dependencies first individually"
    echo "   2. Using the Odoo web interface Apps menu"
    echo "   3. Increasing the timeout value"
else
    echo "❌ Installation failed with exit code: $RESULT"
    echo "   Check the logs above for specific errors."
fi

echo "📝 Installation complete. Check Odoo logs for any additional details."
