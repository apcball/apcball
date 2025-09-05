# Marketplace Settlement - Enhanced Workflow

## หลักการใหม่ (New Principle)

**การแยกการบันทึกค่าธรรมเนียมออกจาก Settlement เพื่อให้ได้เอกสารภาษีที่ถูกต้อง**

ถ้าเราทำ Vendor Bill (Shopee / SPX) เพื่อบันทึกค่าธรรมเนียม + VAT ซื้อ + WHT ตามเอกสารจริง → เราได้ หลักฐานภาษีซื้อ และ หัก ณ ที่จ่าย ครบถ้วน

แปลว่า "ค่าหัก" (deductions) ไม่ควรอยู่ใน Wizard ของ Settlement อีก เพราะมันจะซ้ำซ้อน และ GL จะผิด (ลงค่าใช้จ่าย 2 รอบ)

## โฟลว์ใหม่ที่แนะนำ (Recommended New Workflow)

### 1. ออก Invoice ลูกค้าปลายทาง → รวม Settlement → AR–Shopee
```
Settlement Wizard:
- เลือก Customer Invoices
- สร้าง Settlement
- ได้ AR-Shopee (เต็มจำนวน ไม่หักค่าธรรมเนียม)
```

### 2. สร้าง Vendor Bill แยกต่างหาก
```
Shopee Vendor Bill (TR Number):
- ค่าคอมมิชชั่น
- ค่าบริการ Payment 
- VAT ซื้อ
- หัก ณ ที่จ่าย (ถ้ามี)

SPX Vendor Bill (RC Number):  
- ค่าขนส่ง
- หัก ณ ที่จ่าย 1%
```

### 3. ผูกบิลทั้งหมดเข้ากับ Settlement
```
ใช้ "Link Vendor Bills" action:
- เลือก Vendor Bills ที่เกี่ยวข้อง
- ผูกเข้ากับ Settlement
```

### 4. กดปุ่ม Net-off AP/AR → หักกลบ AR–Shopee และ AP–Shopee
```
ใช้ "Net-off AR/AP" button:
- ดู Preview ก่อน
- ยืนยัน Netting
- ระบบสร้าง Journal Entry หักกลบอัตโนมัติ
```

### 5. Bank Statement → เหลือยอดสุทธิเท่านั้น
```
Reconcile กับ Bank Statement:
- ถ้ายอดสุทธิเป็นบวก: ได้เงินจาก Marketplace
- ถ้ายอดสุทธิเป็นลบ: ต้องจ่ายเงินให้ Marketplace
- ถ้ายอดสุทธิเป็นศูนย์: หักกลบพอดี (ไม่มี Bank Transaction)
```

## ตัวอย่าง Journal Entries

### ก่อน (วิธีเก่า - มีปัญหา):
```
Settlement Entry:
Dr. AR-Customer-A          1,000
Dr. AR-Customer-B          2,000  
Dr. Commission Expense       150  ← บันทึกซ้ำ
Dr. VAT Input Tax             15  ← ไม่มีเอกสารภาษี
Dr. WHT Payable              50   ← ไม่มีใบ รง.3
    Cr. AR-Shopee                 2,865
```

### หลัง (วิธีใหม่ - ถูกต้อง):

**ขั้นตอนที่ 1: Settlement Entry**
```
Dr. AR-Customer-A          1,000
Dr. AR-Customer-B          2,000
    Cr. AR-Shopee                 3,000  ← เต็มจำนวน
```

**ขั้นตอนที่ 2: Shopee Vendor Bill**
```
Dr. Commission Expense       150  ← มีเอกสารภาษี
Dr. VAT Input Tax             15  ← ถูกต้องตาม Input Tax
    Cr. AP-Shopee                  150
    Cr. WHT Payable                 15  ← มีใบ รง.3
```

**ขั้นตอนที่ 3: AR/AP Netting**
```
Dr. AP-Shopee               150
    Cr. AR-Shopee                  150  ← หักกลบ
```

**ผลลัพธ์: AR-Shopee คงเหลือ = 2,850** (ไป reconcile กับ bank)

## การใช้งาน (Usage)

### 1. สร้าง Settlement
```python
# เข้า Accounting > Marketplace Settlement > Create Settlement
# เลือก Trade Channel (Shopee/SPX)
# เลือก Customer Invoices  
# กด Create
```

### 2. สร้าง Vendor Bills
```python
# วิธีที่ 1: ใช้ Quick Actions บน Settlement Form
settlement.action_create_vendor_bill_shopee()  # สำหรับ Shopee
settlement.action_create_vendor_bill_spx()     # สำหรับ SPX

# วิธีที่ 2: สร้างปกติใน Accounting > Vendor Bills
```

### 3. Link Vendor Bills
```python
# บน Settlement Form กด "Link Vendor Bills"
settlement.action_link_vendor_bills()
```

### 4. Preview และ Net-off
```python
# กด "Preview Netting" เพื่อดูยอดก่อน
settlement.action_preview_netting()

# กด "Net-off AR/AP" เพื่อหักกลบ
settlement.action_netoff_ar_ap()
```

### 5. Bank Reconciliation
```python
# กด "Bank Reconciliation" เพื่อ reconcile ยอดสุทธิ
settlement.action_view_bank_reconciliation()
```

## API Methods

### Settlement Wizard (Enhanced)
```python
class MarketplaceSettlementWizard(models.TransientModel):
    # ✅ Removed deduction fields
    # ❌ fee_amount = fields.Monetary(...)  # REMOVED
    # ❌ vat_on_fee_amount = fields.Monetary(...)  # REMOVED  
    # ❌ wht_amount = fields.Monetary(...)  # REMOVED
    
    # ✅ Simplified computation
    @api.depends('invoice_ids')  # No deduction dependencies
    def _compute_total_amount(self):
        record.net_settlement_amount = record.total_amount  # No deductions
```

### Settlement Model (Enhanced)
```python
class MarketplaceSettlement(models.Model):
    # ✅ Enhanced AR/AP netting
    def action_preview_netting(self):
        """Preview AR/AP netting before execution"""
    
    def action_link_vendor_bills(self):
        """Link vendor bills to settlement"""
    
    def action_create_vendor_bill_shopee(self):
        """Quick create Shopee vendor bill"""
    
    def action_create_vendor_bill_spx(self):
        """Quick create SPX vendor bill"""
    
    def get_workflow_status(self):
        """Get current workflow completion status"""
    
    def get_workflow_guidance(self):
        """Get next steps in workflow"""
```

## ประโยชน์ที่ได้ (Benefits)

✅ **เอกสารภาษีถูกต้อง**: Input Tax บันทึกผ่าน Vendor Bill  
✅ **ใบหัก ณ ที่จ่าย**: ผูกกับ Vendor Bill ที่ถูกต้อง  
✅ **ไม่มีการบันทึกซ้ำ**: ค่าธรรมเนียมบันทึกครั้งเดียวใน Vendor Bill  
✅ **Audit Trail ชัดเจน**: เอกสารแยกตามวัตถุประสงค์  
✅ **Reconcile ง่าย**: reconcile แค่ยอดสุทธิกับธนาคาร  
✅ **รายงานดีขึ้น**: แยกประเภท Settlement กับ ค่าธรรมเนียม  
✅ **ตรวจสอบได้**: เอกสารภาษีครบถ้วนสำหรับตรวจสอบ

## Installation

Module นี้ enhance จากโมดูลเดิม ไม่ต้องติดตั้งใหม่:

```bash
# Upgrade existing module
./odoo-bin -u marketplace_settlement

# หรือใน UI: Apps > Marketplace Settlement > Upgrade
```

## Support

สำหรับคำถามหรือปัญหา:
- Email: apcball@example.com  
- Documentation: [NEW_WORKFLOW_IMPLEMENTATION.md](NEW_WORKFLOW_IMPLEMENTATION.md)

---

**สรุป**: โฟลว์ใหม่นี้แยกการทำ Settlement (รวม Invoice ลูกค้า) ออกจากการบันทึกค่าธรรมเนียม (ผ่าน Vendor Bill) เพื่อให้ได้เอกสารภาษีที่ถูกต้อง และ GL ที่แม่นยำ
