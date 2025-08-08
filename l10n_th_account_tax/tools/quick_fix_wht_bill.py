#!/usr/bin/env python3
"""
WHT Bill Calculation Fix - แก้ไขปัญหา WHT ไม่คำนวณในหน้า Bill

รันใน Odoo shell:
odoo-bin shell -d your_database --no-http
exec(open('/path/to/this/script.py').read())
"""

def quick_fix_wht_bill():
    """แก้ไขปัญหา WHT ไม่คำนวณในหน้า Bill ทันที"""
    
    print("🔧 Quick Fix: WHT Bill Calculation")
    print("=" * 50)
    
    fixed_count = 0
    
    # Fix 1: ตรวจสอบและสร้าง WHT Tax Types
    print("1. ตรวจสอบ WHT Tax Types...")
    wht_taxes = env['account.withholding.tax'].search([])
    
    if not wht_taxes:
        print("   ❌ ไม่พบ WHT Tax Types - กำลังสร้าง...")
        
        # สร้าง WHT Account
        wht_account = env['account.account'].create({
            'name': 'WHT Tax Payable',
            'code': '211001',
            'account_type': 'liability_current',
            'wht_account': True,
            'company_id': env.company.id,
        })
        
        # สร้าง WHT Tax Types
        service_wht = env['account.withholding.tax'].create({
            'name': 'Service WHT 3%',
            'amount': 3.0,
            'account_id': wht_account.id,
            'wht_type': 'service',
        })
        
        rental_wht = env['account.withholding.tax'].create({
            'name': 'Rental WHT 5%',
            'amount': 5.0,
            'account_id': wht_account.id,
            'wht_type': 'rental',
        })
        
        print(f"   ✓ สร้าง {service_wht.name}")
        print(f"   ✓ สร้าง {rental_wht.name}")
        fixed_count += 2
    else:
        print(f"   ✓ พบ WHT Tax Types: {len(wht_taxes)} types")
    
    # Fix 2: ตั้งค่า WHT Tax ให้ Products
    print("\n2. ตั้งค่า WHT Tax ให้ Products...")
    
    service_wht = env['account.withholding.tax'].search([
        '|', ('name', 'ilike', 'service'), ('amount', '=', 3)
    ], limit=1)
    
    if service_wht:
        # หา Service Products ที่ยังไม่มี WHT
        service_products = env['product.template'].search([
            ('type', '=', 'service'),
            ('can_be_purchased', '=', True),
            ('supplier_company_wht_tax_id', '=', False),
        ], limit=20)
        
        if service_products:
            for product in service_products:
                product.write({
                    'supplier_company_wht_tax_id': service_wht.id,
                    'supplier_wht_tax_id': service_wht.id,
                })
                print(f"   ✓ {product.name}")
                fixed_count += 1
        else:
            print("   ✓ Service Products มี WHT Tax แล้ว")
    
    # Fix 3: แก้ไข Draft Bills ที่ไม่มี WHT
    print("\n3. แก้ไข Draft Bills...")
    
    if service_wht:
        # หา Draft Bills ที่มี Service แต่ไม่มี WHT
        draft_bills = env['account.move'].search([
            ('move_type', '=', 'in_invoice'),
            ('state', '=', 'draft'),
            ('invoice_line_ids.product_id.type', '=', 'service'),
            ('invoice_line_ids.wht_tax_id', '=', False),
        ], limit=10)
        
        if draft_bills:
            print(f"   กำลังแก้ไข {len(draft_bills)} Bills...")
            
            for bill in draft_bills:
                updated_lines = 0
                for line in bill.invoice_line_ids:
                    if (line.product_id and 
                        line.product_id.type == 'service' and 
                        not line.wht_tax_id):
                        
                        # กำหนด WHT Tax ตาม Partner Type
                        if bill.partner_id.company_type == 'company':
                            line.wht_tax_id = line.product_id.supplier_company_wht_tax_id or service_wht
                        else:
                            line.wht_tax_id = line.product_id.supplier_wht_tax_id or service_wht
                        
                        updated_lines += 1
                
                if updated_lines > 0:
                    print(f"   ✓ {bill.name}: {updated_lines} lines")
                    fixed_count += 1
        else:
            print("   ✓ Draft Bills มี WHT Tax แล้ว")
    
    # Fix 4: Force recompute WHT amounts
    print("\n4. Recompute WHT amounts...")
    
    # หา Bills ที่มี WHT Tax แต่ยังไม่มี WHT Amount
    bills_to_recompute = env['account.move'].search([
        ('move_type', '=', 'in_invoice'),
        ('state', '=', 'draft'),
        ('invoice_line_ids.wht_tax_id', '!=', False),
    ], limit=10)
    
    if bills_to_recompute:
        for bill in bills_to_recompute:
            # Force recompute
            bill.invoice_line_ids._compute_wht_amount()
            
            total_wht = sum([getattr(line, 'wht_amount', 0) for line in bill.invoice_line_ids])
            if total_wht > 0:
                print(f"   ✓ {bill.name}: WHT = {total_wht:,.2f}")
                fixed_count += 1
    
    # สรุปผล
    print("\n" + "=" * 50)
    print("สรุปการแก้ไข:")
    print(f"✓ แก้ไขปัญหาทั้งหมด: {fixed_count} รายการ")
    
    if fixed_count > 0:
        print("\n📋 ขั้นตอนต่อไป:")
        print("1. Refresh หน้าเว็บ (F5)")
        print("2. ตรวจสอบ Bill Draft ที่มีอยู่")
        print("3. สร้าง Bill ใหม่และตรวจสอบ WHT")
        print("4. ดู WHT Tax และ WHT Amount columns")
    else:
        print("\n✅ ระบบ WHT Bill Calculation พร้อมใช้งาน!")
    
    print("=" * 50)
    
    return fixed_count

def test_new_bill():
    """สร้าง Bill ใหม่เพื่อทดสอบ WHT calculation"""
    print("\n🧪 สร้าง Test Bill...")
    
    # หา Product ที่มี WHT
    product = env['product.template'].search([
        ('supplier_company_wht_tax_id', '!=', False),
        ('type', '=', 'service')
    ], limit=1)
    
    if not product:
        print("❌ ไม่พบ Product ที่มี WHT Tax")
        return
    
    # หา Vendor
    vendor = env['res.partner'].search([
        ('supplier_rank', '>', 0),
        ('is_company', '=', True)
    ], limit=1)
    
    if not vendor:
        vendor = env['res.partner'].create({
            'name': 'Test Vendor',
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
    
    # ตรวจสอบ WHT
    for line in bill.invoice_line_ids:
        wht_tax = line.wht_tax_id.name if line.wht_tax_id else "None"
        wht_amount = getattr(line, 'wht_amount', 0)
        print(f"  - Product: {product.name}")
        print(f"  - WHT Tax: {wht_tax}")
        print(f"  - WHT Amount: {wht_amount:,.2f}")
    
    print(f"🎯 Test Bill ID: {bill.id}")
    return bill.id

# รันการแก้ไข
if __name__ == "__main__":
    print("กำลังแก้ไขปัญหา WHT Bill Calculation...")
    
    fixed_count = quick_fix_wht_bill()
    
    if fixed_count > 0:
        print("\n🧪 ทดสอบสร้าง Bill ใหม่...")
        test_bill_id = test_new_bill()
    else:
        print("\nระบบพร้อมใช้งาน! ลองสร้าง Bill ใหม่และตรวจสอบ WHT calculation")
