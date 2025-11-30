#!/bin/bash
# ============================================================================
# Script to fix negative warehouse balance
# Version: 17.0.1.1.1
# ============================================================================

echo "=========================================="
echo "Fix Negative Warehouse Balance"
echo "Version: 17.0.1.1.1"
echo "=========================================="
echo ""

# Database name
DB_NAME="MOG_LIVE"

echo "Step 1: Finding warehouses with negative balance..."
psql -d $DB_NAME -c "
SELECT 
    w.name as \"Warehouse\",
    pt.name as \"Product\",
    SUM(svl.quantity) as \"Total Qty\",
    ROUND(SUM(svl.value)::numeric, 2) as \"Total Value\",
    SUM(svl.remaining_qty) as \"Remaining Qty\",
    ROUND(SUM(svl.remaining_value)::numeric, 2) as \"Remaining Value\"
FROM stock_valuation_layer svl
JOIN stock_warehouse w ON w.id = svl.warehouse_id
JOIN product_product pp ON pp.id = svl.product_id
JOIN product_template pt ON pt.id = pp.product_tmpl_id
WHERE svl.warehouse_id IS NOT NULL
GROUP BY w.name, pt.name
HAVING SUM(svl.remaining_value) < -0.01 OR SUM(svl.remaining_qty) < -0.01
ORDER BY SUM(svl.remaining_value);
"

echo ""
echo "Step 2: Would you like to apply automatic fix? (y/n)"
read -r response

if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
    echo "Applying fixes..."
    
    # Run the Python migration script
    python3 <<PYTHON
import psycopg2
import sys

try:
    conn = psycopg2.connect(dbname='$DB_NAME')
    cur = conn.cursor()
    
    # Import and run migration
    sys.path.insert(0, '/opt/instance1/odoo17/custom-addons/stock_fifo_by_location/migrations/17.0.1.1.1')
    
    print("Running migration script...")
    exec(open('/opt/instance1/odoo17/custom-addons/stock_fifo_by_location/migrations/17.0.1.1.1/post-migrate.py').read())
    
    conn.commit()
    print("✅ Migration completed successfully!")
    
except Exception as e:
    print(f"❌ Error: {str(e)}")
    conn.rollback()
finally:
    conn.close()
PYTHON

    echo ""
    echo "Step 3: Verifying results..."
    psql -d $DB_NAME -c "
    SELECT 
        w.name as \"Warehouse\",
        COUNT(DISTINCT svl.product_id) as \"Products\",
        ROUND(SUM(svl.remaining_value)::numeric, 2) as \"Total Value\",
        CASE 
            WHEN SUM(svl.remaining_value) < 0 THEN '❌ Negative'
            ELSE '✅ Positive'
        END as \"Status\"
    FROM stock_valuation_layer svl
    JOIN stock_warehouse w ON w.id = svl.warehouse_id
    WHERE svl.warehouse_id IS NOT NULL
    GROUP BY w.name
    ORDER BY w.name;
    "
else
    echo "Skipping automatic fix. Please use SQL script manually."
    echo "SQL file location: /opt/instance1/odoo17/custom-addons/stock_fifo_by_location/migrations/17.0.1.1.1/fix_negative_balance.sql"
fi

echo ""
echo "=========================================="
echo "Done!"
echo "=========================================="
