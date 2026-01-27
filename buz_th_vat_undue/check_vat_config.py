#!/usr/bin/env python3
"""
สคริปต์ตรวจสอบ VAT Undue Configuration
รันด้วย: python3 check_vat_config.py
"""

import psycopg2
from psycopg2.extras import RealDictCursor

DB_NAME = "MOG_Pretest2"
DB_USER = "odoo"
DB_PASSWORD = "odoo"  # แก้ไขตามที่ใช้จริง
DB_HOST = "localhost"

def check_configuration():
    try:
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            cursor_factory=RealDictCursor
        )
        cursor = conn.cursor()
        
        print("=" * 80)
        print("1. ตรวจสอบ VAT Undue Tax Configuration")
        print("=" * 80)
        
        cursor.execute("""
            SELECT 
                t.id,
                t.name,
                t.is_vat_undue,
                t.undue_conversion_tax_id,
                t.undue_input_vat_account_id,
                target_tax.name as target_tax_name,
                input_account.code as input_account_code,
                input_account.name as input_account_name
            FROM account_tax t
            LEFT JOIN account_tax target_tax ON t.undue_conversion_tax_id = target_tax.id
            LEFT JOIN account_account input_account ON t.undue_input_vat_account_id = input_account.id
            WHERE t.is_vat_undue = true
            AND t.active = true
        """)
        
        taxes = cursor.fetchall()
        if taxes:
            for tax in taxes:
                print(f"\n📋 Tax: {tax['name']} (ID: {tax['id']})")
                print(f"   ├─ Is VAT Undue: {tax['is_vat_undue']}")
                print(f"   ├─ Target Tax: {tax['target_tax_name']} (ID: {tax['undue_conversion_tax_id']})")
                print(f"   └─ Input VAT Account: {tax['input_account_code']} - {tax['input_account_name']}")
                
                if not tax['input_account_code']:
                    print(f"   ⚠️  WARNING: Input VAT Account not configured!")
                elif tax['input_account_code'] != '116400':
                    print(f"   ⚠️  WARNING: Expected 116400 but got {tax['input_account_code']}")
                else:
                    print(f"   ✅ Configuration OK")
        else:
            print("❌ No VAT Undue tax found!")
        
        print("\n" + "=" * 80)
        print("2. ตรวจสอบบัญชี 116400 และ 116600")
        print("=" * 80)
        
        cursor.execute("""
            SELECT 
                id,
                code,
                name,
                deprecated,
                company_id
            FROM account_account
            WHERE code IN ('116400', '116600')
            ORDER BY code
        """)
        
        accounts = cursor.fetchall()
        for acc in accounts:
            status = "✅ Active" if not acc['deprecated'] else "❌ Deprecated"
            print(f"\n{acc['code']} - {acc['name']}")
            print(f"   ├─ ID: {acc['id']}")
            print(f"   ├─ Company: {acc['company_id']}")
            print(f"   └─ Status: {status}")
        
        print("\n" + "=" * 80)
        print("3. ตรวจสอบ Tax Undue Lines ล่าสุด")
        print("=" * 80)
        
        cursor.execute("""
            SELECT 
                tul.id,
                tul.name,
                tul.tax_amount,
                tul.state,
                undue_acc.code as undue_account_code,
                t.name as tax_name,
                input_acc.code as configured_input_account
            FROM tax_undue_line tul
            LEFT JOIN account_account undue_acc ON tul.account_id = undue_acc.id
            LEFT JOIN account_tax t ON tul.tax_id = t.id
            LEFT JOIN account_account input_acc ON t.undue_input_vat_account_id = input_acc.id
            ORDER BY tul.id DESC
            LIMIT 3
        """)
        
        lines = cursor.fetchall()
        for line in lines:
            print(f"\n📄 Tax Undue Line {line['id']}: {line['name']}")
            print(f"   ├─ Tax: {line['tax_name']}")
            print(f"   ├─ Amount: {line['tax_amount']}")
            print(f"   ├─ State: {line['state']}")
            print(f"   ├─ Undue Account: {line['undue_account_code']}")
            print(f"   └─ Configured Input Account: {line['configured_input_account']}")
            
            if not line['configured_input_account']:
                print(f"   ❌ ERROR: No Input VAT Account configured!")
        
        print("\n" + "=" * 80)
        print("4. ตรวจสอบ Journal Entries ล่าสุด")
        print("=" * 80)
        
        cursor.execute("""
            SELECT 
                am.id,
                am.name,
                am.ref,
                array_agg(aa.code ORDER BY aml.id) as accounts_used,
                array_agg(aml.debit ORDER BY aml.id) as debits,
                array_agg(aml.credit ORDER BY aml.id) as credits
            FROM account_move am
            JOIN account_move_line aml ON am.id = aml.move_id
            JOIN account_account aa ON aml.account_id = aa.id
            WHERE (am.ref LIKE '%Clear Undue VAT%' OR am.ref LIKE '%VAT Usage%')
            GROUP BY am.id, am.name, am.ref
            ORDER BY am.id DESC
            LIMIT 3
        """)
        
        moves = cursor.fetchall()
        for move in moves:
            print(f"\n📝 Move {move['name']}: {move['ref']}")
            print(f"   Accounts used:")
            for idx, (acc, dr, cr) in enumerate(zip(move['accounts_used'], move['debits'], move['credits']), 1):
                print(f"     Line {idx}: {acc} | Dr={dr:.2f}, Cr={cr:.2f}")
            
            # Check if wrong account is used
            if '111002' in move['accounts_used']:
                print(f"   ❌ ERROR: Bank Suspense Account (111002) detected!")
                print(f"   → This means the entry is not balanced or account is missing")
            
            if '116400' in move['accounts_used'] and '116600' in move['accounts_used']:
                print(f"   ✅ Correct accounts used")
            else:
                print(f"   ⚠️  WARNING: Expected accounts 116400 and 116600")
        
        cursor.close()
        conn.close()
        
        print("\n" + "=" * 80)
        print("✅ การตรวจสอบเสร็จสิ้น")
        print("=" * 80)
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    check_configuration()
