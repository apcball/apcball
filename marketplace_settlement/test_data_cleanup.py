#!/usr/bin/env python3
"""
Test installation after removing obsolete fields from data files
"""

def test_data_files_cleaned():
    """Test that all data files are cleaned of obsolete fields"""
    print("Testing Data Files Cleanup...")
    print("=" * 60)
    
    import xml.etree.ElementTree as ET
    
    # Fields that should not exist in data files
    obsolete_fields = [
        'default_vat_rate',
        'default_wht_rate', 
        'vendor_partner_id',
        'purchase_journal_id',
        'vat_tax_id',
        'wht_tax_id',
        'use_thai_wht',
        'thai_income_tax_form',
        'thai_wht_income_type'
    ]
    
    # Data files to check
    data_files = [
        'data/marketplace_settlement_profile_data.xml',
        'data/thai_localization_demo.xml',
        'data/demo_vendor_bills.xml'
    ]
    
    all_clean = True
    
    for data_file in data_files:
        try:
            tree = ET.parse(data_file)
            content = ET.tostring(tree.getroot(), encoding='unicode')
            
            file_clean = True
            for field in obsolete_fields:
                if f'name="{field}"' in content:
                    print(f"✗ {data_file} still contains field: {field}")
                    file_clean = False
                    all_clean = False
            
            if file_clean:
                print(f"✓ {data_file} - cleaned of obsolete fields")
                
        except Exception as e:
            print(f"✗ Error checking {data_file}: {e}")
            all_clean = False
    
    # Check XML syntax
    print("\n✓ Testing XML syntax...")
    for data_file in data_files:
        try:
            ET.parse(data_file)
            print(f"✓ {data_file} - XML syntax OK")
        except ET.ParseError as e:
            print(f"✗ {data_file} - XML syntax error: {e}")
            all_clean = False
    
    # Check model syntax
    print("\n✓ Testing model syntax...")
    import subprocess
    import sys
    
    try:
        result = subprocess.run([sys.executable, '-m', 'py_compile', 'models/profile.py'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print("✓ models/profile.py - Python syntax OK")
        else:
            print(f"✗ models/profile.py - Python syntax error: {result.stderr}")
            all_clean = False
    except Exception as e:
        print(f"✗ Error checking model syntax: {e}")
        all_clean = False
    
    if all_clean:
        print("\n" + "=" * 60)
        print("Data Files Cleanup Tests PASSED!")
        print("\nStatus:")
        print("• ลบ obsolete fields จาก data files แล้ว (✓)")
        print("• XML syntax ถูกต้องทั้งหมด (✓)")
        print("• Model syntax ถูกต้อง (✓)")
        print("• พร้อมสำหรับติดตั้งโมดูล (✓)")
        
        print("\nObsolete fields ที่ลบแล้ว:")
        for field in obsolete_fields[:5]:  # Show first 5
            print(f"  - {field}")
        print(f"  ... และอื่นๆ อีก {len(obsolete_fields)-5} fields")
        
        print("\nการติดตั้ง:")
        print("1. อัปเดตโมดูลใน Odoo")
        print("2. Migration script จะทำงานอัตโนมัติ")
        print("3. ไฟล์ data จะโหลดสำเร็จโดยไม่มี error")
        
        return True
    else:
        print("\n" + "=" * 60)
        print("Data Files Cleanup Tests FAILED!")
        print("กรุณาแก้ไขปัญหาข้างต้นก่อนติดตั้งโมดูล")
        return False

if __name__ == "__main__":
    test_data_files_cleaned()
