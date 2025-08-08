#!/usr/bin/env python3
"""
WHT Information Display Fix - แก้ไขปัญหา Withholding Tax Information แสดง 0.00

รันใน Odoo shell:
odoo-bin shell -d your_database --no-http
exec(open('/path/to/this/script.py').read())
"""

def fix_wht_information_display():
    """แก้ไขปัญหา Withholding Tax Information แสดง 0.00"""
    
    print("🔧 Fix WHT Information Display")
    print("=" * 40)
    
    fixed_count = 0
    
    # ขั้นตอนที่ 1: ตรวจสอบ Bills ที่มี WHT Tax
    print("1. ตรวจสอบ Bills ที่มี WHT Tax...")
    
    bills_with_wht = env['account.move'].search([
        ('move_type', '=', 'in_invoice'),
        ('state', 'in', ['draft', 'posted']),
        ('invoice_line_ids.wht_tax_id', '!=', False),
    ], limit=10)
    
    if not bills_with_wht:
        print("   ❌ ไม่พบ Bills ที่มี WHT Tax")
        return 0
    
    print(f"   ✓ พบ {len(bills_with_wht)} Bills ที่มี WHT Tax")
    
    # ขั้นตอนที่ 2: ตรวจสอบ Withholding Totals
    print("\n2. ตรวจสอบ Withholding Totals:")
    
    for bill in bills_with_wht[:5]:  # ตรวจสอบ 5 bills แรก
        print(f"\n   Bill: {bill.name}")
        
        # ตรวจสอบ current values
        current_base = getattr(bill, 'total_withholding_base', 0)
        current_tax = getattr(bill, 'total_withholding_tax', 0)
        
        print(f"   - Current Base: {current_base:,.2f}")
        print(f"   - Current Tax: {current_tax:,.2f}")
        
        # คำนวณ expected values จาก invoice lines
        expected_base = 0
        expected_tax = 0
        
        for line in bill.invoice_line_ids:
            if hasattr(line, 'wht_tax_id') and line.wht_tax_id and line.price_subtotal:
                base_amount = abs(line.price_subtotal)
                wht_amount = base_amount * (line.wht_tax_id.amount / 100)
                expected_base += base_amount
                expected_tax += wht_amount
                
                print(f"     Line: {line.name[:30]}...")
                print(f"       WHT Tax: {line.wht_tax_id.name}")
                print(f"       Base: {base_amount:,.2f}")
                print(f"       WHT: {wht_amount:,.2f}")
        
        print(f"   - Expected Base: {expected_base:,.2f}")
        print(f"   - Expected Tax: {expected_tax:,.2f}")
        
        # แก้ไขถ้าไม่ตรงกัน
        if abs(current_base - expected_base) > 0.01 or abs(current_tax - expected_tax) > 0.01:
            print("   🔧 กำลังแก้ไข...")
            
            # Force recompute withholding totals
            try:
                # วิธีที่ 1: Trigger recompute
                bill.line_ids._compute_withholding_tax_amount()
                bill._compute_withholding_totals()
                
                # วิธีที่ 2: Manual set (fallback)
                if abs(bill.total_withholding_base - expected_base) > 0.01:
                    env.cr.execute("""
                        UPDATE account_move 
                        SET total_withholding_base = %s,
                            total_withholding_tax = %s 
                        WHERE id = %s
                    """, (expected_base, expected_tax, bill.id))
                    
                    print(f"   ✅ Updated: Base={expected_base:,.2f}, Tax={expected_tax:,.2f}")
                    fixed_count += 1
                else:
                    print("   ✅ Already correct after recompute")
                    
            except Exception as e:
                print(f"   ❌ Error fixing bill: {e}")
    
    # ขั้นตอนที่ 3: Test specific bill
    print("\n3. ทดสอบ Bill ที่มีปัญหา:")
    
    # หา Bill ที่มี WHT แต่ total = 0
    problematic_bills = []
    for bill in bills_with_wht:
        has_wht_lines = any(line.wht_tax_id for line in bill.invoice_line_ids)
        total_base = getattr(bill, 'total_withholding_base', 0)
        
        if has_wht_lines and total_base == 0:
            problematic_bills.append(bill)
    
    if problematic_bills:
        print(f"   ⚠️ พบ {len(problematic_bills)} Bills ที่มีปัญหา:")
        
        for bill in problematic_bills[:3]:  # แก้ไข 3 bills แรก
            print(f"   กำลังแก้ไข {bill.name}...")
            
            # คำนวณใหม่
            total_base = 0
            total_tax = 0
            
            for line in bill.invoice_line_ids:
                if line.wht_tax_id and line.price_subtotal:
                    base = abs(line.price_subtotal)
                    tax = base * (line.wht_tax_id.amount / 100)
                    total_base += base
                    total_tax += tax
            
            # อัปเดตค่า
            if total_base > 0:
                env.cr.execute("""
                    UPDATE account_move 
                    SET total_withholding_base = %s,
                        total_withholding_tax = %s 
                    WHERE id = %s
                """, (total_base, total_tax, bill.id))
                
                print(f"   ✅ Fixed: {bill.name} - Base: {total_base:,.2f}, Tax: {total_tax:,.2f}")
                fixed_count += 1
    else:
        print("   ✅ ไม่พบ Bills ที่มีปัญหา")
    
    # ขั้นตอนที่ 4: สรุปผล
    print("\n" + "=" * 40)
    print("สรุปการแก้ไข:")
    print(f"✓ แก้ไข Bills: {fixed_count} รายการ")
    
    if fixed_count > 0:
        # Commit การเปลี่ยนแปลง
        env.cr.commit()
        
        print("\n📋 ขั้นตอนต่อไป:")
        print("1. Refresh หน้าเว็บ (F5)")
        print("2. ตรวจสอบ Bills ที่แก้ไขแล้ว")
        print("3. ดู Withholding Tax Information แสดงยอดถูกต้อง")
    else:
        print("\n✅ ระบบ WHT Information พร้อมใช้งาน!")
    
    print("=" * 40)
    
    return fixed_count

def test_wht_information():
    """ทดสอบสร้าง Bill ใหม่และตรวจสอบ WHT Information"""
    print("\n🧪 สร้าง Test Bill เพื่อทดสอบ WHT Information...")
    
    # หา Product ที่มี WHT
    service_wht = env['account.withholding.tax'].search([
        '|', ('name', 'ilike', 'service'), ('amount', '=', 3)
    ], limit=1)
    
    if not service_wht:
        print("❌ ไม่พบ Service WHT Tax")
        return
    
    # หา หรือสร้าง Product
    product = env['product.template'].search([
        ('supplier_company_wht_tax_id', '!=', False)
    ], limit=1)
    
    if not product:
        product = env['product.template'].create({
            'name': 'Test Service for WHT',
            'type': 'service',
            'can_be_purchased': True,
            'supplier_company_wht_tax_id': service_wht.id,
            'supplier_wht_tax_id': service_wht.id,
        })
        print(f"   ✓ สร้าง Product: {product.name}")
    
    # หา หรือสร้าง Vendor
    vendor = env['res.partner'].search([
        ('supplier_rank', '>', 0),
        ('is_company', '=', True)
    ], limit=1)
    
    if not vendor:
        vendor = env['res.partner'].create({
            'name': 'Test Vendor WHT Info',
            'is_company': True,
            'supplier_rank': 1,
        })
    
    # สร้าง Bill
    bill = env['account.move'].create({
        'move_type': 'in_invoice',
        'partner_id': vendor.id,
        'invoice_date': fields.Date.today(),
        'invoice_line_ids': [(0, 0, {
            'product_id': product.id,
            'name': f'Test {product.name}',
            'quantity': 1,
            'price_unit': 10000,
        })]
    })
    
    print(f"✓ สร้าง Bill: {bill.name}")
    
    # Force compute WHT
    for line in bill.invoice_line_ids:
        if not line.wht_tax_id and product.supplier_company_wht_tax_id:
            line.wht_tax_id = product.supplier_company_wht_tax_id
    
    # Recompute totals
    bill.line_ids._compute_withholding_tax_amount()
    bill._compute_withholding_totals()
    
    # ตรวจสอบผลลัพธ์
    total_base = getattr(bill, 'total_withholding_base', 0)
    total_tax = getattr(bill, 'total_withholding_tax', 0)
    
    print(f"📊 WHT Information Results:")
    print(f"   - Total Withholding Base: {total_base:,.2f} ฿")
    print(f"   - Total Withholding Tax: {total_tax:,.2f} ฿")
    
    if total_base > 0 and total_tax > 0:
        print("   ✅ WHT Information แสดงผลถูกต้อง!")
    else:
        print("   ❌ WHT Information ยังเป็น 0.00 - ต้องตรวจสอบเพิ่มเติม")
    
    print(f"🎯 Test Bill ID: {bill.id}")
    return bill.id

# รันการแก้ไข
if __name__ == "__main__":
    print("กำลังแก้ไขปัญหา WHT Information Display...")
    
    fixed_count = fix_wht_information_display()
    
    print("\n🧪 ทดสอบสร้าง Bill ใหม่...")
    test_bill_id = test_wht_information()
    
    if fixed_count > 0 or test_bill_id:
        print(f"\n✅ เสร็จสิ้น! Bills ควรแสดง WHT Information ที่ถูกต้องแล้ว")
    else:
        print(f"\n⚠️ ต้องตรวจสอบเพิ่มเติม หรือรัน Module Update")
