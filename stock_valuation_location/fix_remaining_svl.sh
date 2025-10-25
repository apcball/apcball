#!/bin/bash
###############################################################################
# Fix the 2 remaining SVL records without location
# Simple and safe script
###############################################################################

if [ -z "$1" ]; then
    echo "Usage: $0 <database_name>"
    exit 1
fi

DB_NAME="$1"

cd /opt/instance1/odoo17

echo "🔧 Fixing 2 SVL records without location..."
echo ""

./odoo-bin shell -c /etc/instance1.conf -d "$DB_NAME" <<'PYTHON_CODE'
# หา 2 records ที่ยังไม่มี location
svls_no_loc = env["stock.valuation.layer"].search([
    ("stock_move_id", "!=", False),
    ("location_id", "=", False)
])

print("=" * 70)
print(f"Found {len(svls_no_loc)} SVL records without location")
print("=" * 70)

if len(svls_no_loc) == 0:
    print("✅ All done! No records to fix.")
else:
    print("\n📋 Details of records to fix:")
    print("-" * 70)
    
    for svl in svls_no_loc:
        move = svl.stock_move_id
        print(f"\nSVL ID: {svl.id}")
        print(f"  Product: {svl.product_id.name}")
        print(f"  Quantity: {svl.quantity}")
        print(f"  Value: {svl.value}")
        
        if move:
            print(f"  Move: {move.reference or move.name}")
            print(f"  From: {move.location_id.complete_name} (usage: {move.location_id.usage})")
            print(f"  To: {move.location_dest_id.complete_name} (usage: {move.location_dest_id.usage})")
        else:
            print("  No stock move attached")
    
    print("\n" + "-" * 70)
    print("\n🔄 Recomputing location for these records...")
    
    # Recompute
    svls_no_loc._compute_location_id()
    
    print("✅ Recompute completed!")
    
    # Verify
    print("\n📊 Verification:")
    for svl in svls_no_loc:
        loc_name = svl.location_id.complete_name if svl.location_id else "❌ Still no location"
        print(f"  SVL {svl.id}: {loc_name}")

print("\n" + "=" * 70)
print("Done!")
exit()
PYTHON_CODE

echo ""
echo "✅ Script completed!"
