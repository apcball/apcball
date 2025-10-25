#!/bin/bash
###############################################################################
# Check Stock Valuation Layer Statistics
# Usage: ./check_svl_stats.sh <database_name>
###############################################################################

if [ -z "$1" ]; then
    echo "Usage: $0 <database_name>"
    echo ""
    echo "Example: $0 my_database"
    exit 1
fi

DB_NAME="$1"

cd /opt/instance1/odoo17

echo "Checking SVL statistics for database: $DB_NAME"
echo ""

./odoo-bin shell -c /etc/instance1.conf -d "$DB_NAME" <<'PYTHON_CODE'
# ตรวจสอบจำนวน SVL records
try:
    total_svl = env["stock.valuation.layer"].search_count([])
    svl_with_moves = env["stock.valuation.layer"].search_count([("stock_move_id", "!=", False)])
    svl_with_location = env["stock.valuation.layer"].search_count([("location_id", "!=", False)])
    
    print("=" * 70)
    print("📊 Stock Valuation Layer Statistics")
    print("=" * 70)
    print(f"Total SVL records:              {total_svl:>15,}")
    print(f"SVL with stock moves:           {svl_with_moves:>15,}")
    print(f"SVL with location computed:     {svl_with_location:>15,}")
    print(f"SVL without location:           {(svl_with_moves - svl_with_location):>15,}")
    print("=" * 70)
    print("")
    
    if total_svl == 0:
        print("⚠️  สถานะ: ไม่มีข้อมูล Stock Valuation Layer ในระบบ")
        print("   → นี่คือ database ใหม่ หรือยังไม่มีการเคลื่อนไหวสินค้า")
        print("   → Module ติดตั้งสำเร็จแล้ว พร้อมใช้งาน!")
    elif svl_with_moves == 0:
        print("⚠️  สถานะ: มี SVL แต่ไม่มีที่เชื่อมกับ stock moves")
        print("   → อาจเป็น Landed Cost SVL เท่านั้น")
        print("   → ไม่ต้องทำ recompute")
    elif svl_with_location == svl_with_moves:
        print("✅ สถานะ: ทุก SVL ที่มี moves มี location ครบถ้วนแล้ว!")
        print("   → Module ทำงานปกติ ไม่ต้อง recompute")
        print("   → พร้อมใช้งาน!")
    else:
        missing = svl_with_moves - svl_with_location
        print(f"⚠️  สถานะ: มี {missing:,} records ที่ยังไม่มี location")
        print(f"   → ควร run recompute")
        print("")
        print("   วิธีแก้:")
        print("   1. ใช้ ORM Recompute (ใน UI)")
        print("      Inventory → Configuration → Recompute SVL Location (ORM)")
        print("")
        print("   2. หรือใช้ SQL Fast Path (สำหรับข้อมูลเยอะ)")
        print("      Inventory → Configuration → SVL Location — Fast SQL")
    
    print("")
    print("=" * 70)
    
    # แสดงตัวอย่าง SVL
    if total_svl > 0:
        print("")
        print("📋 ตัวอย่าง Stock Valuation Layer (5 records ล่าสุด):")
        print("=" * 70)
        svls = env["stock.valuation.layer"].search([], limit=5, order='id desc')
        for svl in svls:
            move_ref = svl.stock_move_id.reference if svl.stock_move_id else "No Move"
            loc_name = svl.location_id.complete_name if svl.location_id else "No Location"
            print(f"ID: {svl.id:>6} | Product: {svl.product_id.name[:30]:<30} | Loc: {loc_name[:25]:<25}")
        print("=" * 70)
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

exit()
PYTHON_CODE

echo ""
echo "Done!"
