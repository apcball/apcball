#!/usr/bin/env python3
"""
WHT Auto Fill Quick Fix Script
แก้ไขปัญหา WHT ไม่ Auto Fill ให้ทำงานได้

รันใน Odoo shell:
odoo-bin shell -d your_database --no-http
exec(open('/path/to/this/script.py').read())
"""

def fix_wht_auto_fill():
    """แก้ไขปัญหา WHT Auto Fill ทันที"""
    
    print("=" * 60)
    print("WHT Auto Fill Quick Fix")
    print("=" * 60)
    
    fixed_count = 0
    
    # Fix 1: ตรวจสอบและสร้าง WHT Accounts ที่ขาดหาย
    print("\n1. ตรวจสอบ WHT Accounts...")
    
    wht_accounts = env['account.account'].search([('wht_account', '=', True)])
    if not wht_accounts:
        print("   ❌ ไม่พบ WHT Accounts - กำลังสร้าง...")
        
        # หา Company
        company = env.company
        
        # สร้าง WHT Accounts
        wht_service_account = env['account.account'].create({
            'name': 'WHT Service Tax Payable',
            'code': '211001',
            'account_type': 'liability_current',
            'wht_account': True,
            'company_id': company.id,
        })
        
        wht_rental_account = env['account.account'].create({
            'name': 'WHT Rental Tax Payable', 
            'code': '211002',
            'account_type': 'liability_current',
            'wht_account': True,
            'company_id': company.id,
        })
        
        print(f"   ✓ สร้าง {wht_service_account.name}")
        print(f"   ✓ สร้าง {wht_rental_account.name}")
        fixed_count += 1
    else:
        print(f"   ✓ พบ WHT Accounts: {len(wht_accounts)} accounts")
    
    # Fix 2: ตรวจสอบและสร้าง WHT Tax Types
    print("\n2. ตรวจสอบ WHT Tax Types...")
    
    wht_taxes = env['account.withholding.tax'].search([])
    if not wht_taxes:
        print("   ❌ ไม่พบ WHT Tax Types - กำลังสร้าง...")
        
        # หา WHT Accounts
        service_account = env['account.account'].search([
            ('wht_account', '=', True),
            '|', ('name', 'ilike', 'service'), ('code', '=', '211001')
        ], limit=1)
        
        rental_account = env['account.account'].search([
            ('wht_account', '=', True), 
            '|', ('name', 'ilike', 'rental'), ('code', '=', '211002')
        ], limit=1)
        
        if not service_account:
            service_account = wht_accounts[0] if wht_accounts else None
        if not rental_account:
            rental_account = wht_accounts[1] if len(wht_accounts) > 1 else service_account
        
        # สร้าง WHT Tax Types
        if service_account:
            service_wht = env['account.withholding.tax'].create({
                'name': 'Service WHT 3%',
                'amount': 3.0,
                'account_id': service_account.id,
                'wht_type': 'service',
            })
            print(f"   ✓ สร้าง {service_wht.name}")
            fixed_count += 1
        
        if rental_account:
            rental_wht = env['account.withholding.tax'].create({
                'name': 'Rental WHT 5%',
                'amount': 5.0,
                'account_id': rental_account.id,
                'wht_type': 'rental',
            })
            print(f"   ✓ สร้าง {rental_wht.name}")
            fixed_count += 1
    else:
        print(f"   ✓ พบ WHT Tax Types: {len(wht_taxes)} types")
        
        # ตรวจสอบ WHT Tax Types มี Account หรือไม่
        for tax in wht_taxes:
            if not tax.account_id:
                print(f"   ⚠️ {tax.name} ไม่มี Account - กำลังแก้ไข...")
                
                # หา Account ที่เหมาะสม
                if 'service' in tax.name.lower() or tax.amount == 3:
                    account = env['account.account'].search([
                        ('wht_account', '=', True),
                        '|', ('name', 'ilike', 'service'), ('code', '=', '211001')
                    ], limit=1)
                elif 'rental' in tax.name.lower() or tax.amount == 5:
                    account = env['account.account'].search([
                        ('wht_account', '=', True),
                        '|', ('name', 'ilike', 'rental'), ('code', '=', '211002')
                    ], limit=1)
                else:
                    account = wht_accounts[0] if wht_accounts else None
                
                if account:
                    tax.account_id = account.id
                    print(f"     ✓ กำหนด Account: {account.name}")
                    fixed_count += 1
    
    # Fix 3: ตั้งค่า WHT Tax ให้ Products
    print("\n3. ตั้งค่า WHT Tax ให้ Products...")
    
    service_wht = env['account.withholding.tax'].search([
        '|', ('name', 'ilike', 'service'), ('amount', '=', 3)
    ], limit=1)
    
    if service_wht:
        # หา Service Products ที่ยังไม่มี WHT
        service_products = env['product.template'].search([
            ('type', '=', 'service'),
            ('can_be_purchased', '=', True),
            ('supplier_company_wht_tax_id', '=', False),
        ])
        
        if service_products:
            print(f"   กำลังตั้งค่า WHT Tax ให้ {len(service_products)} Service Products...")
            
            for product in service_products[:10]:  # ตั้งค่าแค่ 10 ตัวแรก
                product.write({
                    'supplier_company_wht_tax_id': service_wht.id,
                    'supplier_wht_tax_id': service_wht.id,
                })
                print(f"   ✓ {product.name}")
                fixed_count += 1
        else:
            print("   ✓ Service Products มี WHT Tax แล้ว")
    
    # Fix 4: แก้ไข Invoice Lines ที่มีอยู่
    print("\n4. แก้ไข Invoice Lines ที่ขาดหาย WHT Tax...")
    
    # หา Draft/Posted Invoices ที่มี Service แต่ไม่มี WHT
    invoices = env['account.move'].search([
        ('move_type', 'in', ['in_invoice', 'in_refund']),
        ('state', 'in', ['draft', 'posted']),
        ('line_ids.product_id.type', '=', 'service'),
        ('line_ids.wht_tax_id', '=', False),
    ], limit=20)
    
    if invoices and service_wht:
        print(f"   กำลังแก้ไข {len(invoices)} Invoices...")
        
        for invoice in invoices:
            updated_lines = 0
            for line in invoice.line_ids:
                if (line.product_id and 
                    line.product_id.type == 'service' and 
                    not line.wht_tax_id and
                    line.debit > 0):  # เฉพาะ expense lines
                    
                    # กำหนด WHT Tax ตาม Partner Type
                    if invoice.partner_id.company_type == 'company':
                        wht_tax = line.product_id.supplier_company_wht_tax_id or service_wht
                    else:
                        wht_tax = line.product_id.supplier_wht_tax_id or service_wht
                    
                    if wht_tax:
                        line.wht_tax_id = wht_tax.id
                        updated_lines += 1
            
            if updated_lines > 0:
                print(f"   ✓ {invoice.name}: {updated_lines} lines")
                fixed_count += 1
    else:
        print("   ✓ Invoice Lines มี WHT Tax แล้ว")
    
    # Fix 5: Test Payment Register
    print("\n5. ทดสอบ Payment Register Auto Fill...")
    
    # หา Invoice ที่มี WHT Tax
    test_invoice = env['account.move'].search([
        ('move_type', '=', 'in_invoice'),
        ('state', '=', 'posted'),
        ('payment_state', '!=', 'paid'),
        ('line_ids.wht_tax_id', '!=', False),
    ], limit=1)
    
    if test_invoice:
        print(f"   ทดสอบกับ Invoice: {test_invoice.name}")
        
        # สร้าง Payment Register
        try:
            payment_ctx = {
                'active_model': 'account.move',
                'active_ids': [test_invoice.id],
            }
            
            payment_wizard = env['account.payment.register'].with_context(**payment_ctx).create({
                'payment_date': fields.Date.today(),
            })
            
            # ตรวจสอบ Auto Fill
            original_amount = test_invoice.amount_total
            payment_amount = payment_wizard.amount
            wht_base = getattr(payment_wizard, 'wht_amount_base', 0)
            
            print(f"   - Original: {original_amount:,.2f}")
            print(f"   - Payment: {payment_amount:,.2f}")
            print(f"   - WHT Base: {wht_base:,.2f}")
            
            if wht_base > 0 and payment_amount < original_amount:
                print("   ✅ WHT Auto Fill ทำงานได้!")
            else:
                print("   ⚠️ WHT Auto Fill ยังไม่ทำงาน - ลอง Refresh Module")
                
        except Exception as e:
            print(f"   ❌ Error testing payment: {e}")
    else:
        print("   ⚠️ ไม่พบ Invoice สำหรับทดสอบ")
    
    # สรุปผล
    print("\n" + "=" * 60)
    print("สรุปการแก้ไข:")
    print(f"✓ แก้ไขปัญหาทั้งหมด: {fixed_count} รายการ")
    
    if fixed_count > 0:
        print("\n📋 ขั้นตอนต่อไป:")
        print("1. Update Module: l10n_th_account_tax")
        print("2. Restart Odoo Server") 
        print("3. Clear Browser Cache")
        print("4. ทดสอบสร้าง Invoice + Payment Register ใหม่")
        print("5. ดู MANUAL_TESTING_GUIDE_TH.md สำหรับวิธีทดสอบ")
    else:
        print("\n✅ ระบบ WHT Auto Fill พร้อมใช้งาน!")
    
    print("=" * 60)
    
    return fixed_count

# Quick commands สำหรับแก้ไขปัญหาเฉพาะ
def fix_product_wht():
    """แก้ไขเฉพาะ Product WHT Tax"""
    service_wht = env['account.withholding.tax'].search([('amount', '=', 3)], limit=1)
    if not service_wht:
        print("❌ ไม่พบ Service WHT 3%")
        return
    
    products = env['product.template'].search([
        ('type', '=', 'service'),
        ('supplier_company_wht_tax_id', '=', False),
    ])
    
    for product in products:
        product.write({
            'supplier_company_wht_tax_id': service_wht.id,
            'supplier_wht_tax_id': service_wht.id,
        })
    
    print(f"✓ ตั้งค่า WHT Tax ให้ {len(products)} Products")

def fix_invoice_wht():
    """แก้ไขเฉพาะ Invoice Lines WHT Tax"""
    service_wht = env['account.withholding.tax'].search([('amount', '=', 3)], limit=1)
    if not service_wht:
        print("❌ ไม่พบ Service WHT 3%")
        return
    
    lines = env['account.move.line'].search([
        ('move_id.move_type', '=', 'in_invoice'),
        ('product_id.type', '=', 'service'),
        ('wht_tax_id', '=', False),
        ('debit', '>', 0),
    ])
    
    for line in lines:
        line.wht_tax_id = service_wht.id
    
    print(f"✓ ตั้งค่า WHT Tax ให้ {len(lines)} Invoice Lines")

# รันการแก้ไข
if __name__ == "__main__":
    print("กำลังแก้ไขปัญหา WHT Auto Fill...")
    fixed_count = fix_wht_auto_fill()
    
    if fixed_count == 0:
        print("\nไม่มีปัญหาที่ต้องแก้ไข หรือรัน Quick Fix Commands:")
        print("fix_product_wht()  # แก้ไข Product WHT")
        print("fix_invoice_wht()  # แก้ไข Invoice WHT")
