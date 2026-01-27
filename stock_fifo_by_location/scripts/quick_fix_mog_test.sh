#!/bin/bash
# -*- coding: utf-8 -*-
"""
Quick Start Script สำหรับแก้ไข Valuation ใน MOG_TEST

วิธีใช้:
  chmod +x quick_fix_mog_test.sh
  ./quick_fix_mog_test.sh
"""

ODOO_PATH="/opt/instance1/odoo17"
DATABASE="MOG_TEST"
SCRIPT_PATH="/opt/instance1/odoo17/custom-addons/stock_fifo_by_location/scripts"

echo "=================================="
echo "Quick Fix Valuation - MOG_TEST"
echo "=================================="
echo ""

# ตรวจสอบว่า Odoo instance ทำงานหรือไม่
echo "🔍 ตรวจสอบสถานะ Odoo instance..."
systemctl is-active --quiet instance1
if [ $? -eq 0 ]; then
    echo "⚠️  Odoo instance กำลังทำงานอยู่"
    echo "   แนะนำให้ stop instance ก่อนรัน script"
    echo ""
    read -p "ต้องการ stop instance และดำเนินการต่อ? (y/n): " confirm
    if [ "$confirm" == "y" ]; then
        echo "🛑 หยุด Odoo instance..."
        sudo systemctl stop instance1
        sleep 2
    else
        echo "❌ ยกเลิกการทำงาน"
        exit 1
    fi
else
    echo "✅ Odoo instance หยุดทำงานแล้ว"
fi

echo ""
echo "📋 เลือกการทำงาน:"
echo "  1) แก้ไขข้อมูล valuation ที่มีอยู่ (Fix existing data)"
echo "  2) ยกของเข้าคลัง (Create initial stock)"
echo "  3) ดูตัวอย่างการใช้งาน (Examples)"
echo "  4) เปิด Odoo Shell (Manual)"
echo ""
read -p "เลือก (1-4): " choice

cd "$ODOO_PATH"

case $choice in
    1)
        echo ""
        echo "=================================="
        echo "แก้ไขข้อมูล Valuation (Dry Run)"
        echo "=================================="
        echo ""
        python3 odoo-bin shell -d "$DATABASE" --no-http << 'EOFPYTHON'
execfile('/opt/instance1/odoo17/custom-addons/stock_fifo_by_location/scripts/fix_valuation_by_warehouse.py')

# รัน dry run
print("\n🔍 กำลังวิเคราะห์ข้อมูล (Dry Run)...\n")
stats = fix_valuation_by_warehouse(env, dry_run=True)

print("\n" + "="*80)
print("ผลลัพธ์จาก Dry Run")
print("="*80)
print(f"จำนวน layers ที่จะแก้ไข warehouse_id: {stats['fixed_warehouse']}")
print(f"จำนวน layers ที่จะแก้ไข remaining: {stats['fixed_remaining']}")
print(f"จำนวน errors: {stats['errors']}")
print("="*80)

print("\n⚠️  นี่เป็นการทดสอบเท่านั้น ข้อมูลยังไม่ถูกบันทึก")
print("\nถ้าต้องการบันทึกจริง ให้รันคำสั่ง:")
print("  fix_valuation_by_warehouse(env, dry_run=False)")
print("\nหรือเลือกตัวเลือก 1 อีกครั้งแล้วยืนยันการบันทึก")
EOFPYTHON

        echo ""
        read -p "ต้องการบันทึกข้อมูลจริงหรือไม่? (yes/no): " confirm
        if [ "$confirm" == "yes" ]; then
            echo ""
            echo "💾 กำลังบันทึกข้อมูล..."
            echo ""
            python3 odoo-bin shell -d "$DATABASE" --no-http << 'EOFPYTHON'
execfile('/opt/instance1/odoo17/custom-addons/stock_fifo_by_location/scripts/fix_valuation_by_warehouse.py')
stats = fix_valuation_by_warehouse(env, dry_run=False)
print("\n✅ บันทึกข้อมูลเรียบร้อยแล้ว!")
EOFPYTHON
        else
            echo "ℹ️  ยกเลิกการบันทึก"
        fi
        ;;
    
    2)
        echo ""
        echo "=================================="
        echo "ยกของเข้าคลัง"
        echo "=================================="
        echo ""
        echo "กรุณาป้อนข้อมูล:"
        read -p "  รหัสสินค้า (Product Code): " product_code
        read -p "  รหัสคลัง (Warehouse Code): " warehouse_code
        read -p "  จำนวน (Quantity): " quantity
        read -p "  ราคาต้นทุน (Unit Cost): " unit_cost
        read -p "  คำอธิบาย (Description): " description
        
        echo ""
        echo "📋 ข้อมูลที่จะบันทึก:"
        echo "  สินค้า: $product_code"
        echo "  คลัง: $warehouse_code"
        echo "  จำนวน: $quantity"
        echo "  ราคา: $unit_cost"
        echo "  คำอธิบาย: $description"
        echo ""
        
        python3 odoo-bin shell -d "$DATABASE" --no-http << EOFPYTHON
execfile('/opt/instance1/odoo17/custom-addons/stock_fifo_by_location/scripts/create_initial_stock_by_warehouse.py')

# ทดสอบก่อน
print("\n🔍 กำลังทดสอบ (Dry Run)...\n")
result = create_initial_stock_layer(
    env,
    product_code='$product_code',
    warehouse_code='$warehouse_code',
    quantity=float('$quantity'),
    unit_cost=float('$unit_cost'),
    description='$description',
    dry_run=True
)

if result['success']:
    print("✅ ทดสอบผ่าน!")
    print(f"สินค้า: {result['product']}")
    print(f"คลัง: {result['warehouse']}")
    print(f"จำนวน: {result['quantity']:,.2f}")
    print(f"ราคา: {result['unit_cost']:,.2f}")
    print(f"มูลค่ารวม: {result['value']:,.2f}")
else:
    print(f"❌ เกิดข้อผิดพลาด: {result.get('error')}")
EOFPYTHON

        echo ""
        read -p "ต้องการบันทึกข้อมูลจริงหรือไม่? (yes/no): " confirm
        if [ "$confirm" == "yes" ]; then
            echo ""
            echo "💾 กำลังบันทึกข้อมูล..."
            echo ""
            python3 odoo-bin shell -d "$DATABASE" --no-http << EOFPYTHON
execfile('/opt/instance1/odoo17/custom-addons/stock_fifo_by_location/scripts/create_initial_stock_by_warehouse.py')
result = create_initial_stock_layer(
    env,
    product_code='$product_code',
    warehouse_code='$warehouse_code',
    quantity=float('$quantity'),
    unit_cost=float('$unit_cost'),
    description='$description',
    dry_run=False
)
if result['success']:
    print(f"\n✅ บันทึกเรียบร้อย!")
    print(f"Move ID: {result.get('move_id')}")
    print(f"Layer ID: {result.get('layer_id')}")
else:
    print(f"\n❌ เกิดข้อผิดพลาด: {result.get('error')}")
EOFPYTHON
        else
            echo "ℹ️  ยกเลิกการบันทึก"
        fi
        ;;
    
    3)
        echo ""
        echo "=================================="
        echo "ตัวอย่างการใช้งาน"
        echo "=================================="
        cat "$SCRIPT_PATH/README.md"
        ;;
    
    4)
        echo ""
        echo "=================================="
        echo "เปิด Odoo Shell"
        echo "=================================="
        echo ""
        echo "💡 คำสั่งที่น่าสนใจ:"
        echo ""
        echo "# โหลด script แก้ไข valuation"
        echo "execfile('$SCRIPT_PATH/fix_valuation_by_warehouse.py')"
        echo "fix_valuation_by_warehouse(env, dry_run=True)"
        echo ""
        echo "# โหลด script สร้าง stock"
        echo "execfile('$SCRIPT_PATH/create_initial_stock_by_warehouse.py')"
        echo "example_usage(env)"
        echo ""
        echo "---"
        echo ""
        python3 odoo-bin shell -d "$DATABASE" --no-http
        ;;
    
    *)
        echo "❌ ตัวเลือกไม่ถูกต้อง"
        exit 1
        ;;
esac

echo ""
echo "=================================="
echo "เสร็จสิ้น"
echo "=================================="
echo ""

# ถามว่าต้องการ restart instance หรือไม่
read -p "ต้องการ restart Odoo instance หรือไม่? (y/n): " restart
if [ "$restart" == "y" ]; then
    echo "🔄 กำลัง restart Odoo instance..."
    sudo systemctl start instance1
    sleep 2
    systemctl is-active --quiet instance1
    if [ $? -eq 0 ]; then
        echo "✅ Odoo instance เริ่มทำงานแล้ว"
    else
        echo "⚠️  ไม่สามารถ start instance ได้ กรุณาตรวจสอบ"
    fi
else
    echo "ℹ️  อย่าลืม start instance ด้วยคำสั่ง: sudo systemctl start instance1"
fi

echo ""
echo "🎉 ขอบคุณที่ใช้งาน!"
echo ""
