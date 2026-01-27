#!/usr/bin/env python3
"""
Debug script สำหรับตรวจสอบ Netting Logic
ใช้วิเคราะห์ว่าทำไม Netting Entry ไม่มี Receivable
"""

def analyze_netting_issue():
    """วิเคราะห์ปัญหา Netting ที่ไม่มี Receivable"""
    print("="*70)
    print("การวิเคราะห์ปัญหา AR/AP Netting")
    print("="*70)
    
    print("\n📋 สิ่งที่เห็นใน Journal Entry:")
    print("   Reference: AR/AP Netting - SETTLE-SHOPEE-20250908")
    print("   Dr. 211200 เจ้าหนี้การค้าในประเทศ  214.00")
    print("   Cr. 211200 เจ้าหนี้การค้าในประเทศ  214.00")
    
    print("\n🚨 ปัญหาที่พบ:")
    print("   ❌ ไม่มี Receivable Account ใน Netting Entry")
    print("   ❌ มีแต่ Payable Account เท่านั้น")
    print("   ❌ ไม่ได้ทำ AR/AP Netting จริงๆ")
    
    print("\n🔍 สาเหตุที่เป็นไปได้:")
    print("   1. Settlement ไม่มี Move ID")
    print("   2. Settlement Move ไม่มี Receivable Lines")
    print("   3. Receivable Lines ถูก Reconcile ไปแล้ว")
    print("   4. Partner ไม่ match")
    print("   5. Account Type Detection ผิดพลาด")
    print("   6. Settlement Amount = 0")
    
    print("\n💡 วิธีตรวจสอบ:")
    print("   1. ดู Settlement Record และ Move ID")
    print("   2. ตรวจสอบ Move Lines ของ Settlement")
    print("   3. ดู Partner ID ที่ใช้")
    print("   4. ตรวจสอบ Account Types")
    print("   5. ดูสถานะ Reconciled")
    
    print("\n🛠️  วิธีแก้ไข:")
    print("   1. เพิ่ม Debug Logging ใน _create_netting_move()")
    print("   2. ตรวจสอบเงื่อนไขการหา Receivable Lines")
    print("   3. ตรวจสอบ Account Type Detection")
    print("   4. เพิ่ม Validation ก่อนสร้าง Netting Entry")
    
    print("\n🎯 Entry ที่ถูกต้องควรเป็น:")
    print("   สมมติ Settlement Amount = 1000, Vendor Bill = 214:")
    print("   Dr. Payable Account      214.00  (ลบ AP)")
    print("   Cr. Receivable Account  1000.00  (ลบ AR)")
    print("   Dr. Receivable Account   786.00  (Net AR)")
    
    print("\n   หรือ Settlement Amount = 214, Vendor Bill = 214:")
    print("   Dr. Payable Account      214.00  (ลบ AP)")
    print("   Cr. Receivable Account   214.00  (ลบ AR)")
    print("   (Perfect Netting - ไม่มี Net Balance)")

def suggest_debugging_steps():
    """แนะนำขั้นตอนการ Debug"""
    print("\n" + "="*70)
    print("ขั้นตอนการ Debug")
    print("="*70)
    
    print("\n1. เพิ่ม Logging ใน _create_netting_move():")
    print("   - Log Settlement Move ID")
    print("   - Log จำนวน Settlement Receivable Lines ที่พบ")
    print("   - Log Partner ID ที่ใช้")
    print("   - Log Account Types ที่ detect ได้")
    print("   - Log สถานะ Reconciled")
    
    print("\n2. ตรวจสอบ Settlement Record:")
    print("   - Settlement: SETTLE-SHOPEE-20250908")
    print("   - Move ID: มีหรือไม่")
    print("   - Partner: Shopee")
    print("   - Invoice Amount: เท่าไหร่")
    
    print("\n3. ตรวจสอบ Vendor Bills:")
    print("   - Bill Amount: 214.00")
    print("   - Partner: Shopee (ต้องเป็น Partner เดียวกัน)")
    print("   - Account: 211200")
    
    print("\n4. Test Cases ที่ควรทำ:")
    print("   - Settlement with Receivable > Payable")
    print("   - Settlement with Receivable = Payable")
    print("   - Settlement with Receivable < Payable")

if __name__ == "__main__":
    analyze_netting_issue()
    suggest_debugging_steps()
    
    print("\n" + "="*70)
    print("สรุป: ต้องเพิ่ม Debug เพื่อหาสาเหตุที่ Receivable ไม่ถูกพบ")
    print("="*70)
