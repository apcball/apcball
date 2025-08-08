#!/usr/bin/env python3
"""
WHT Auto Fill Test Script
ใช้สำหรับทดสอบ WHT auto fill ใน Odoo

รันใน Odoo shell:
odoo-bin shell -d your_database --no-http
exec(open('/path/to/this/script.py').read())
"""

def test_wht_auto_fill():
    """ทดสอบ WHT auto fill functionality"""
    
    print("=" * 60)
    print("WHT Auto Fill Test Script")
    print("=" * 60)
    
    # ขั้นตอนที่ 1: ตรวจสอบ WHT Tax Types
    print("\n1. ตรวจสอบ WHT Tax Types:")
    wht_taxes = env['account.withholding.tax'].search([])
    if not wht_taxes:
        print("❌ ไม่พบ WHT Tax Types - ต้องสร้างก่อน")
        return False
    
    for tax in wht_taxes:
        print(f"   ✓ {tax.name} ({tax.amount}%) - Account: {tax.account_id.name if tax.account_id else 'No Account'}")
    
    # ขั้นตอนที่ 2: ตรวจสอบ Products
    print("\n2. ตรวจสอบ Products มี WHT Tax:")
    products_with_wht = env['product.template'].search([
        '|', 
        ('supplier_wht_tax_id', '!=', False),
        ('supplier_company_wht_tax_id', '!=', False)
    ])
    
    if not products_with_wht:
        print("❌ ไม่มี Products ที่ตั้งค่า WHT Tax")
        print("   กำลังตั้งค่า Product ตัวอย่าง...")
        
        # สร้าง Product ตัวอย่าง
        service_wht = wht_taxes.filtered(lambda t: 'service' in t.name.lower() or '3' in t.name)
        if service_wht:
            test_product = env['product.template'].create({
                'name': 'ค่าบริการ Testing',
                'type': 'service',
                'can_be_purchased': True,
                'supplier_company_wht_tax_id': service_wht[0].id,
                'supplier_wht_tax_id': service_wht[0].id,
                'standard_price': 10000,
            })
            print(f"   ✓ สร้าง Product: {test_product.name}")
        else:
            print("   ❌ ไม่พบ Service WHT Tax สำหรับตั้งค่า Product")
    else:
        for product in products_with_wht[:5]:  # แสดง 5 ตัวแรก
            company_wht = product.supplier_company_wht_tax_id.name if product.supplier_company_wht_tax_id else "None"
            individual_wht = product.supplier_wht_tax_id.name if product.supplier_wht_tax_id else "None"
            print(f"   ✓ {product.name} - Company WHT: {company_wht}, Individual WHT: {individual_wht}")
    
    # ขั้นตอนที่ 3: สร้าง Test Vendor
    print("\n3. สร้าง Test Vendor:")
    test_vendor = env['res.partner'].search([('name', '=', 'Test Vendor WHT')], limit=1)
    if not test_vendor:
        test_vendor = env['res.partner'].create({
            'name': 'Test Vendor WHT',
            'is_company': True,
            'supplier_rank': 1,
            'vat': '1234567890123',
        })
        print(f"   ✓ สร้าง Vendor: {test_vendor.name}")
    else:
        print(f"   ✓ ใช้ Vendor ที่มีอยู่: {test_vendor.name}")
    
    # ขั้นตอนที่ 4: สร้าง Test Invoice
    print("\n4. สร้าง Test Invoice:")
    
    # หา Product ที่มี WHT
    test_product = env['product.template'].search([('supplier_company_wht_tax_id', '!=', False)], limit=1)
    if not test_product:
        print("   ❌ ไม่พบ Product ที่มี WHT Tax")
        return False
    
    # สร้าง Invoice
    invoice_vals = {
        'move_type': 'in_invoice',
        'partner_id': test_vendor.id,
        'invoice_date': fields.Date.today(),
        'invoice_line_ids': [(0, 0, {
            'product_id': test_product.id,
            'name': f'Test {test_product.name}',
            'quantity': 1,
            'price_unit': 10000,
        })]
    }
    
    test_invoice = env['account.move'].create(invoice_vals)
    print(f"   ✓ สร้าง Invoice: {test_invoice.name}")
    
    # ตรวจสอบ WHT ใน Invoice Lines
    wht_lines = test_invoice.line_ids.filtered('wht_tax_id')
    if wht_lines:
        for line in wht_lines:
            print(f"   ✓ Line มี WHT: {line.name} - WHT Tax: {line.wht_tax_id.name}")
    else:
        print("   ⚠️ Invoice Lines ยังไม่มี WHT Tax - กำลังตั้งค่า...")
        
        # Auto-assign WHT Tax
        for line in test_invoice.line_ids:
            if line.product_id and not line.wht_tax_id:
                if test_vendor.company_type == 'company':
                    line.wht_tax_id = line.product_id.supplier_company_wht_tax_id
                else:
                    line.wht_tax_id = line.product_id.supplier_wht_tax_id
                
                if line.wht_tax_id:
                    print(f"   ✓ กำหนด WHT Tax: {line.wht_tax_id.name} ให้กับ {line.name}")
    
    # Confirm Invoice
    test_invoice.action_post()
    print(f"   ✓ Confirm Invoice: {test_invoice.state}")
    
    # ขั้นตอนที่ 5: ทดสอบ Payment Register
    print("\n5. ทดสอบ Payment Register:")
    
    # สร้าง Payment Register Wizard
    payment_ctx = {
        'active_model': 'account.move',
        'active_ids': [test_invoice.id],
    }
    
    payment_wizard = env['account.payment.register'].with_context(**payment_ctx).create({
        'payment_date': fields.Date.today(),
    })
    
    print(f"   ✓ สร้าง Payment Register")
    print(f"   - Original Amount: 10,000")
    print(f"   - Payment Amount: {payment_wizard.amount}")
    print(f"   - WHT Base: {getattr(payment_wizard, 'wht_amount_base', 0)}")
    print(f"   - WHT Tax: {payment_wizard.wht_tax_id.name if payment_wizard.wht_tax_id else 'None'}")
    print(f"   - Writeoff Account: {payment_wizard.writeoff_account_id.name if payment_wizard.writeoff_account_id else 'None'}")
    print(f"   - Payment Difference Handling: {payment_wizard.payment_difference_handling}")
    
    # ตรวจสอบผลลัพธ์
    expected_wht = 10000 * 0.03  # 3% WHT
    expected_payment = 10000 - expected_wht
    
    if abs(payment_wizard.amount - expected_payment) < 1:  # ใกล้เคียงกับที่คาดหวัง
        print("   ✅ WHT Auto Fill ทำงานถูกต้อง!")
        
        # ทดสอบสร้าง Payment
        try:
            payments = payment_wizard._create_payments()
            payment = payments[0] if payments else None
            
            if payment:
                print(f"   ✓ สร้าง Payment: {payment.name}")
                print(f"   - Amount: {payment.amount}")
                print(f"   - State: {payment.state}")
                
                # ตรวจสอบ Journal Entry
                move_lines = payment.move_id.line_ids
                wht_lines = move_lines.filtered(lambda l: 'WHT' in (l.account_id.name or '') or l.account_id.wht_account)
                
                if wht_lines:
                    print("   ✓ พบ WHT Journal Entry:")
                    for line in wht_lines:
                        print(f"     - {line.account_id.name}: {line.credit}")
                else:
                    print("   ⚠️ ไม่พบ WHT Journal Entry")
                    
        except Exception as e:
            print(f"   ❌ Error creating payment: {e}")
            
    else:
        print("   ❌ WHT Auto Fill ไม่ทำงาน:")
        print(f"     - Expected: {expected_payment}")
        print(f"     - Actual: {payment_wizard.amount}")
        print("     - ตรวจสอบการตั้งค่า WHT Tax และ Product")
    
    # ขั้นตอนที่ 6: สรุปผล
    print("\n" + "=" * 60)
    print("สรุปผลการทดสอบ:")
    
    if abs(payment_wizard.amount - expected_payment) < 1:
        print("✅ WHT Auto Fill ทำงานปกติ - พร้อมใช้งาน!")
    else:
        print("❌ WHT Auto Fill ไม่ทำงาน - ต้องแก้ไข:")
        print("   1. ตรวจสอบ Product มี WHT Tax")
        print("   2. ตรวจสอบ Invoice Line มี WHT Tax")
        print("   3. ตรวจสอบ Payment Register Wizard")
        print("   4. อ่าน WHT_AUTO_FILL_FIX.md สำหรับวิธีแก้ไข")
    
    print("=" * 60)
    
    return test_invoice.id

# รันการทดสอบ
if __name__ == "__main__":
    print("กำลังทดสอบ WHT Auto Fill...")
    test_invoice_id = test_wht_auto_fill()
    if test_invoice_id:
        print(f"\nTest Invoice ID: {test_invoice_id}")
        print("สามารถใช้ ID นี้สำหรับทดสอบเพิ่มเติม")
