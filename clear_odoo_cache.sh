#!/bin/bash
# Clear Odoo assets cache and force reload

echo "============================================"
echo "Clearing Odoo Assets Cache"
echo "============================================"
echo ""

# Database name
DB_NAME="MOG_LIVE_15_08"

echo "Step 1: Stopping Odoo instance..."
sudo systemctl stop instance1
sleep 2
echo "✓ Stopped"
echo ""

echo "Step 2: Clearing assets cache..."
# Clear ir.attachment assets
/opt/instance1/odoo17-venv/bin/python3 << EOF
import psycopg2
try:
    conn = psycopg2.connect(
        dbname="$DB_NAME",
        user="odoo",
        password="odoo",
        host="localhost"
    )
    cur = conn.cursor()
    
    # Delete assets attachments
    cur.execute("DELETE FROM ir_attachment WHERE name LIKE 'web.assets%'")
    deleted = cur.fetchone()
    
    conn.commit()
    print(f"✓ Cleared {cur.rowcount} asset cache entries")
    
    cur.close()
    conn.close()
except Exception as e:
    print(f"✗ Error: {e}")
    print("Note: You may need to clear cache via Odoo UI instead")
EOF

echo ""
echo "Step 3: Starting Odoo instance..."
sudo systemctl start instance1
sleep 3

if systemctl is-active --quiet instance1; then
    echo "✓ Instance started"
    echo ""
    echo "============================================"
    echo "Cache Cleared!"
    echo "============================================"
    echo ""
    echo "IMPORTANT: Now do the following:"
    echo "1. Close your browser completely"
    echo "2. Open browser again"
    echo "3. Go to Odoo and do a HARD REFRESH:"
    echo "   - Chrome/Firefox: Ctrl+Shift+R"
    echo "   - Or: Ctrl+F5"
    echo "4. Try deleting a voucher again"
else
    echo "✗ Failed to start instance"
fi
