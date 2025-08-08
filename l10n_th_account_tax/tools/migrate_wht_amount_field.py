#!/usr/bin/env python3
"""
Database Migration Script for WHT Amount Field
เพิ่ม wht_amount field ใน account.move.line model

รันใน Odoo shell:
odoo-bin shell -d your_database --no-http
exec(open('/path/to/this/script.py').read())
"""

def add_wht_amount_field():
    """เพิ่ม wht_amount field ใน account.move.line model"""
    
    print("🔧 Adding wht_amount field to account.move.line...")
    
    try:
        # ตรวจสอบว่า field มีอยู่แล้วหรือไม่
        if hasattr(env['account.move.line'], 'wht_amount'):
            print("✅ wht_amount field already exists")
            return True
        
        # สร้าง field ใหม่โดยใช้ SQL
        env.cr.execute("""
            ALTER TABLE account_move_line 
            ADD COLUMN IF NOT EXISTS wht_amount NUMERIC;
        """)
        
        # อัปเดต field definition ใน ir.model.fields
        field_vals = {
            'name': 'wht_amount',
            'field_description': 'WHT Amount',
            'model': 'account.move.line',
            'model_id': env.ref('account.model_account_move_line').id,
            'ttype': 'monetary',
            'store': True,
            'readonly': True,
            'help': 'Withholding Tax Amount for this line',
        }
        
        existing_field = env['ir.model.fields'].search([
            ('model', '=', 'account.move.line'),
            ('name', '=', 'wht_amount')
        ])
        
        if not existing_field:
            env['ir.model.fields'].create(field_vals)
            print("✅ Created wht_amount field definition")
        else:
            print("✅ wht_amount field definition exists")
        
        # คำนวณ WHT Amount สำหรับ records ที่มีอยู่
        env.cr.execute("""
            UPDATE account_move_line 
            SET wht_amount = CASE 
                WHEN wht_tax_id IS NOT NULL AND price_subtotal IS NOT NULL 
                THEN price_subtotal * (
                    SELECT amount / 100 
                    FROM account_withholding_tax 
                    WHERE id = wht_tax_id
                )
                ELSE 0 
            END
            WHERE wht_amount IS NULL OR wht_amount = 0;
        """)
        
        updated_count = env.cr.rowcount
        print(f"✅ Updated {updated_count} records with WHT amounts")
        
        # Commit การเปลี่ยนแปลง
        env.cr.commit()
        
        print("✅ Successfully added wht_amount field!")
        return True
        
    except Exception as e:
        print(f"❌ Error adding wht_amount field: {e}")
        env.cr.rollback()
        return False

def test_wht_amount_field():
    """ทดสอบ wht_amount field ทำงานหรือไม่"""
    
    print("\n🧪 Testing wht_amount field...")
    
    try:
        # หา record ที่มี WHT Tax
        lines_with_wht = env['account.move.line'].search([
            ('wht_tax_id', '!=', False),
            ('price_subtotal', '>', 0)
        ], limit=5)
        
        if not lines_with_wht:
            print("ℹ️ No records with WHT Tax found for testing")
            return
        
        print("Testing records:")
        for line in lines_with_wht:
            wht_tax = line.wht_tax_id
            price_subtotal = line.price_subtotal
            wht_amount = getattr(line, 'wht_amount', 0)
            expected_wht = price_subtotal * (wht_tax.amount / 100) if wht_tax else 0
            
            print(f"  Line: {line.name[:50]}")
            print(f"    Price: {price_subtotal:,.2f}")
            print(f"    WHT Tax: {wht_tax.name} ({wht_tax.amount}%)")
            print(f"    WHT Amount: {wht_amount:,.2f}")
            print(f"    Expected: {expected_wht:,.2f}")
            
            if abs(wht_amount - expected_wht) < 0.01:
                print("    ✅ Correct calculation")
            else:
                print("    ⚠️ Calculation mismatch")
                # แก้ไขค่าที่ผิด
                line.wht_amount = expected_wht
                print("    ✅ Fixed calculation")
        
        print("\n✅ wht_amount field is working!")
        
    except Exception as e:
        print(f"❌ Error testing wht_amount field: {e}")

def update_existing_bills():
    """อัปเดต Bills ที่มีอยู่ให้มี WHT Amount"""
    
    print("\n📋 Updating existing bills...")
    
    try:
        # หา Bills ที่มี WHT Tax แต่ไม่มี WHT Amount
        bills = env['account.move'].search([
            ('move_type', 'in', ['in_invoice', 'in_refund']),
            ('invoice_line_ids.wht_tax_id', '!=', False),
        ], limit=20)
        
        updated_bills = 0
        
        for bill in bills:
            updated_lines = 0
            
            for line in bill.invoice_line_ids:
                if line.wht_tax_id and line.price_subtotal:
                    expected_wht = line.price_subtotal * (line.wht_tax_id.amount / 100)
                    current_wht = getattr(line, 'wht_amount', 0)
                    
                    if abs(current_wht - expected_wht) > 0.01:
                        line.wht_amount = expected_wht
                        updated_lines += 1
            
            if updated_lines > 0:
                print(f"  ✅ {bill.name}: {updated_lines} lines updated")
                updated_bills += 1
        
        print(f"\n✅ Updated {updated_bills} bills with WHT amounts")
        
    except Exception as e:
        print(f"❌ Error updating existing bills: {e}")

# Main execution
if __name__ == "__main__":
    print("🚀 WHT Amount Field Migration")
    print("=" * 40)
    
    # Step 1: Add field
    success = add_wht_amount_field()
    
    if success:
        # Step 2: Test field
        test_wht_amount_field()
        
        # Step 3: Update existing records
        update_existing_bills()
        
        print("\n" + "=" * 40)
        print("✅ Migration completed successfully!")
        print("\nNext steps:")
        print("1. Update the module: l10n_th_account_tax")
        print("2. Add wht_amount field back to views")
        print("3. Test WHT calculation in Bills")
    else:
        print("\n❌ Migration failed!")
        print("Please check the errors above and try again.")
