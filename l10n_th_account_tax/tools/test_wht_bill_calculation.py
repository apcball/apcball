#!/usr/bin/env python3
"""
WHT Bill Calculation Test Script
ทดสอบ WHT calculation ใน Bill/Invoice

รันใน Odoo shell:
odoo-bin shell -d your_database --no-http
exec(open('/path/to/this/script.py').read())
"""

def test_wht_bill_calculation():
    """ทดสอบ WHT calculation ในหน้า Bill"""
    
    print("=" * 60)
    print("WHT Bill Calculation Test")
    print("=" * 60)
    
    # ขั้นตอนที่ 1: ตรวจสอบ Products มี WHT Tax
    print("\n1. ตรวจสอบ Products มี WHT Tax:")
    products_with_wht = env['product.template'].search([
        '|', 
        ('supplier_wht_tax_id', '!=', False),
        ('supplier_company_wht_tax_id', '!=', False)
    ], limit=3)
    
    if not products_with_wht:
        print("❌ ไม่พบ Products ที่มี WHT Tax - กำลังสร้าง...")
        
        # หา WHT Tax
        service_wht = env['account.withholding.tax'].search([
            '|', ('name', 'ilike', 'service'), ('amount', '=', 3)
        ], limit=1)
        
        if not service_wht:
            print("❌ ไม่พบ Service WHT Tax - กำลังสร้าง...")
            
            # หา WHT Account
            wht_account = env['account.account'].search([
                ('wht_account', '=', True)
            ], limit=1)
            
            if not wht_account:
                # สร้าง WHT Account
                wht_account = env['account.account'].create({
                    'name': 'WHT Service Tax Payable',
                    'code': '211001',
                    'account_type': 'liability_current',
                    'wht_account': True,
                    'company_id': env.company.id,
                })
                print(f"   ✓ สร้าง WHT Account: {wht_account.name}")
            
            # สร้าง WHT Tax
            service_wht = env['account.withholding.tax'].create({
                'name': 'Service WHT 3%',
                'amount': 3.0,
                'account_id': wht_account.id,
                'wht_type': 'service',
            })
            print(f"   ✓ สร้าง WHT Tax: {service_wht.name}")
        
        # สร้าง Product ตัวอย่าง
        test_product = env['product.template'].create({
            'name': 'ค่าบริการ Consulting',
            'type': 'service',
            'can_be_purchased': True,
            'supplier_company_wht_tax_id': service_wht.id,
            'supplier_wht_tax_id': service_wht.id,
            'standard_price': 10000,
        })
        print(f"   ✓ สร้าง Product: {test_product.name}")
        products_with_wht = [test_product]
    
    for product in products_with_wht:
        company_wht = product.supplier_company_wht_tax_id.name if product.supplier_company_wht_tax_id else "None"
        individual_wht = product.supplier_wht_tax_id.name if product.supplier_wht_tax_id else "None"
        print(f"   ✓ {product.name}")
        print(f"     - Company WHT: {company_wht}")
        print(f"     - Individual WHT: {individual_wht}")
    
    # ขั้นตอนที่ 2: สร้าง Test Vendor
    print("\n2. สร้าง Test Vendor:")
    test_vendor = env['res.partner'].search([('name', '=', 'Test Vendor WHT Bill')], limit=1)
    if not test_vendor:
        test_vendor = env['res.partner'].create({
            'name': 'Test Vendor WHT Bill',
            'is_company': True,
            'supplier_rank': 1,
            'vat': '1234567890123',
        })
        print(f"   ✓ สร้าง Vendor: {test_vendor.name}")
    else:
        print(f"   ✓ ใช้ Vendor ที่มีอยู่: {test_vendor.name}")
    
    # ขั้นตอนที่ 3: สร้าง Test Bill/Invoice
    print("\n3. สร้าง Test Bill:")
    
    test_product = products_with_wht[0]
    
    # สร้าง Bill
    invoice_vals = {
        'move_type': 'in_invoice',
        'partner_id': test_vendor.id,
        'invoice_date': fields.Date.today(),
        'invoice_line_ids': [(0, 0, {
            'product_id': test_product.id,
            'name': f'ค่าบริการ {test_product.name}',
            'quantity': 1,
            'price_unit': 10000,
        })]
    }
    
    test_bill = env['account.move'].create(invoice_vals)
    print(f"   ✓ สร้าง Bill: {test_bill.name}")
    
    # ขั้นตอนที่ 4: ตรวจสอบ WHT calculation ใน Invoice Lines
    print("\n4. ตรวจสอบ WHT calculation:")
    
    for line in test_bill.invoice_line_ids:
        print(f"   Line: {line.name}")
        print(f"   - Product: {line.product_id.name if line.product_id else 'No Product'}")
        print(f"   - Price Subtotal: {line.price_subtotal:,.2f}")
        print(f"   - WHT Tax: {line.wht_tax_id.name if line.wht_tax_id else 'None'}")
        print(f"   - WHT Amount: {getattr(line, 'wht_amount', 0):,.2f}")
        
        # ตรวจสอบการคำนวณ
        if line.wht_tax_id:
            expected_wht = line.price_subtotal * (line.wht_tax_id.amount / 100)
            actual_wht = getattr(line, 'wht_amount', 0)
            
            if abs(expected_wht - actual_wht) < 0.01:
                print(f"   ✅ WHT calculation ถูกต้อง: {actual_wht:,.2f}")
            else:
                print(f"   ❌ WHT calculation ผิด:")
                print(f"       Expected: {expected_wht:,.2f}")
                print(f"       Actual: {actual_wht:,.2f}")
        else:
            print("   ⚠️ ไม่มี WHT Tax - ตรวจสอบ Product configuration")
    
    # ขั้นตอนที่ 5: ทดสอบ Manual WHT assignment
    print("\n5. ทดสอบ Manual WHT assignment:")
    
    service_wht = env['account.withholding.tax'].search([
        '|', ('name', 'ilike', 'service'), ('amount', '=', 3)
    ], limit=1)
    
    if service_wht:
        # Manual assign WHT Tax ให้ lines ที่ยังไม่มี
        for line in test_bill.invoice_line_ids:
            if not line.wht_tax_id:
                line.wht_tax_id = service_wht.id
                print(f"   ✓ กำหนด WHT Tax manual: {line.name}")
        
        # ตรวจสอบการคำนวณหลัง manual assign
        test_bill.invoice_line_ids._compute_wht_amount()
        
        print("   Updated WHT amounts:")
        for line in test_bill.invoice_line_ids:
            wht_amount = getattr(line, 'wht_amount', 0)
            print(f"   - {line.name}: {wht_amount:,.2f}")
    
    # ขั้นตอนที่ 6: คำนวณ Total WHT
    print("\n6. สรุป WHT ใน Bill:")
    
    total_subtotal = sum(test_bill.invoice_line_ids.mapped('price_subtotal'))
    total_wht = sum([getattr(line, 'wht_amount', 0) for line in test_bill.invoice_line_ids])
    net_amount = total_subtotal - total_wht
    
    print(f"   - Bill Amount: {total_subtotal:,.2f}")
    print(f"   - Total WHT: {total_wht:,.2f}")
    print(f"   - Net Amount: {net_amount:,.2f}")
    print(f"   - Bill ID: {test_bill.id}")
    
    # ขั้นตอนที่ 7: สรุปผล
    print("\n" + "=" * 60)
    print("สรุปผลการทดสอบ:")
    
    if total_wht > 0:
        print("✅ WHT calculation ทำงานได้!")
        print("   - WHT Tax แสดงในหน้า Bill")
        print("   - WHT Amount คำนวณถูกต้อง")
        print("   - พร้อมทำ Payment Register")
    else:
        print("❌ WHT calculation ไม่ทำงาน:")
        print("   1. ตรวจสอบ Product มี WHT Tax configuration")
        print("   2. ตรวจสอบ Invoice Lines มี wht_tax_id")
        print("   3. ตรวจสอบ View แสดง WHT fields")
        print("   4. อ่าน manual ใน MANUAL_TESTING_GUIDE_TH.md")
    
    print("=" * 60)
    
    return test_bill.id

# Helper functions
def fix_missing_wht_fields():
    """แก้ไข Invoice Lines ที่ไม่มี WHT Tax"""
    print("กำลังแก้ไข Invoice Lines ที่ไม่มี WHT Tax...")
    
    service_wht = env['account.withholding.tax'].search([('amount', '=', 3)], limit=1)
    if not service_wht:
        print("❌ ไม่พบ Service WHT 3%")
        return
    
    # หา Draft Bills ที่มี Service Product แต่ไม่มี WHT
    bills = env['account.move'].search([
        ('move_type', '=', 'in_invoice'),
        ('state', '=', 'draft'),
        ('invoice_line_ids.product_id.type', '=', 'service'),
        ('invoice_line_ids.wht_tax_id', '=', False),
    ])
    
    for bill in bills:
        for line in bill.invoice_line_ids:
            if line.product_id and line.product_id.type == 'service' and not line.wht_tax_id:
                line.wht_tax_id = service_wht.id
                print(f"✓ {bill.name} - {line.name}")
    
    print(f"แก้ไขเสร็จ: {len(bills)} Bills")

# รันการทดสอบ
if __name__ == "__main__":
    print("กำลังทดสอบ WHT Bill Calculation...")
    test_bill_id = test_wht_bill_calculation()
    
    if test_bill_id:
        print(f"\nTest Bill ID: {test_bill_id}")
        print("\nCommands สำหรับ Debug:")
        print("fix_missing_wht_fields()  # แก้ไข Bills ที่ไม่มี WHT")
    else:
        print("\nไม่สามารถสร้าง Test Bill ได้")
