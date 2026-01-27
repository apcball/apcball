#!/usr/bin/env python3
"""
Test Netting with Debug Logging
ทดสอบ netting และดู debug information
"""

def create_test_instructions():
    """สร้างคำแนะนำสำหรับการทดสอบ"""
    print("="*70)
    print("คำแนะนำการทดสอบ Netting พร้อม Debug Logging")
    print("="*70)
    
    print("\n📋 ขั้นตอนการทดสอบ:")
    print("1. Update module marketplace_settlement")
    print("2. ไปที่ Settlement: SETTLE-SHOPEE-20250908")
    print("3. กดปุ่ม 'Reverse Netting' (ถ้ามี) เพื่อ undo netting เก่า")
    print("4. กดปุ่ม 'AR/AP Netting Wizard' หรือ 'Quick Netting' อีกครั้ง")
    print("5. ตรวจสอบ Debug Logs")
    
    print("\n📍 ที่ดู Debug Logs:")
    print("Settings → Technical → Logging → Logging")
    print("หรือ")
    print("Settings → Technical → Database Structure → Logging")
    print("กรอง: name = 'marketplace_settlement_debug'")
    
    print("\n🔍 ข้อมูลที่ต้องดู:")
    print("1. Settlement Move ID")
    print("2. Marketplace Partner")
    print("3. Settlement Move Lines (ทั้งหมด)")
    print("4. Filtered Receivable Lines Count")
    print("5. Vendor Bill Lines (ทั้งหมด)")
    print("6. Total Receivable/Payable Amount")
    print("7. Netting Lines Count")
    
    print("\n❓ คำถามที่ต้องตอบ:")
    print("1. Settlement Move มี Receivable Lines หรือไม่?")
    print("2. Partner ID ตรงกันหรือไม่?")
    print("3. Account Type Detection ถูกต้องหรือไม่?")
    print("4. Lines ถูก Reconcile ไปแล้วหรือไม่?")
    
    print("\n🎯 ผลลัพธ์ที่คาดหวัง:")
    print("ถ้า Settlement Amount > 0:")
    print("   - ควรมี Receivable Lines")
    print("   - Total Receivable Amount > 0")
    print("   - Netting Lines ควรมี AR และ AP")
    
    print("\nถ้า Settlement Amount = 0:")
    print("   - ไม่มี Receivable Lines (ปกติ)")
    print("   - Total Receivable Amount = 0")
    print("   - Netting Lines มีแต่ AP (ปกติ)")

def analyze_current_situation():
    """วิเคราะห์สถานการณ์ปัจจุบัน"""
    print("\n" + "="*70)
    print("การวิเคราะห์สถานการณ์ปัจจุบัน")
    print("="*70)
    
    print("\n🔍 สิ่งที่เห็นใน Entry ปัจจุบัน:")
    print("   Dr. Payable 214.00")
    print("   Cr. Payable 214.00")
    
    print("\n🤔 สมมติฐาน:")
    print("A. Settlement Amount = 0")
    print("   → ไม่มี Receivable Lines")
    print("   → มีแต่ Payable Processing")
    print("   → Entry ยกเลิก + สร้าง AP ใหม่")
    
    print("\nB. Settlement Amount > 0 แต่ถูก Reconcile แล้ว")
    print("   → Receivable Lines ถูกกรอง out")
    print("   → เหลือแต่ Payable")
    
    print("\nC. Partner ไม่ match")
    print("   → Settlement Partner ≠ Vendor Bill Partner")
    print("   → ไม่เจอ Receivable Lines")
    
    print("\nD. Account Type Detection ผิด")
    print("   → Receivable Account ไม่ถูก detect เป็น 'receivable'")
    
    print("\n✅ Debug Logs จะช่วยให้รู้ว่าเป็นกรณีไหน")

def next_steps():
    """ขั้นตอนต่อไป"""
    print("\n" + "="*70)
    print("ขั้นตอนต่อไป")
    print("="*70)
    
    print("\n1. 🔄 Update Module:")
    print("   Apps → marketplace_settlement → Update")
    
    print("\n2. 🧪 ทดสอบ Netting ใหม่:")
    print("   - ไปที่ Settlement")
    print("   - Reverse Netting เก่า (ถ้ามี)")
    print("   - ทำ Netting ใหม่")
    
    print("\n3. 📊 ดู Debug Logs:")
    print("   - ไปที่ Logging")
    print("   - หา 'marketplace_settlement_debug'")
    print("   - วิเคราะห์ข้อมูล")
    
    print("\n4. 🔧 แก้ไขตาม Debug Info:")
    print("   - ถ้าไม่มี Receivable: ตรวจสอบ Settlement")
    print("   - ถ้า Partner ไม่ match: แก้ Partner")
    print("   - ถ้า Account Type ผิด: แก้ Detection Logic")

if __name__ == "__main__":
    create_test_instructions()
    analyze_current_situation()
    next_steps()
    
    print("\n" + "="*70)
    print("✅ พร้อมทดสอบและวิเคราะห์ปัญหา Netting")
    print("="*70)
