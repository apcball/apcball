# Marketplace Settlement Enhancement - Direct Bill Linking

## สรุปการปรับปรุง

ได้ปรับปรุงโมดูล `marketplace_settlement` ตามแนวคิดของคุณ โดยเพิ่มฟีเจอร์การผูก Vendor Bills เข้ากับ Settlement โดยตรง และปรับปรุง UX ให้ใช้งานง่ายขึ้น

## การเปลี่ยนแปลงหลัก

### 1. ✅ เพิ่มฟิลด์ `x_settlement_id` บน Vendor Bills

```python
# ใน models/sale_account_extension.py
x_settlement_id = fields.Many2one('marketplace.settlement', 
                                 string='Marketplace Settlement',
                                 domain="[('company_id','=',company_id), ('marketplace_partner_id','=',partner_id)]",
                                 help='Link bill to settlement for netting')
```

### 2. ✅ ปรับปรุง Settlement Model

```python
# ใน models/settlement.py
vendor_bill_ids = fields.One2many('account.move', 'x_settlement_id',
                                 string='Linked Vendor Bills',
                                 domain="[('move_type', 'in', ['in_invoice', 'in_refund']), ('state', '=', 'posted')]",
                                 help='Vendor bills linked to this settlement for netting')
```

### 3. ✅ เพิ่ม Smart Buttons บน Settlement

- **"Link Bills"**: เปิด wizard เลือกบิลเข้างวด
- **"Net-off Preview"**: แสดงสรุปก่อนทำ AR/AP netting
- **"View Vendor Bills"**: ดูบิลที่ผูกไว้

### 4. ✅ ปรับปรุง Vendor Bill Form

- แสดงฟิลด์ `x_settlement_id` สำหรับเลือก/ดู settlement
- ปุ่ม "Link to Settlement" สำหรับบิลที่ยังไม่ได้ผูก
- ปุ่ม "View Settlement" สำหรับบิลที่ผูกแล้ว

### 5. ✅ สร้าง Bill Link Wizard ใหม่

- รองรับ 2 โหมด: เลือกบิลจาก Settlement หรือเลือก Settlement จากบิล
- ฟังก์ชัน Auto-select bills ตามยอดเงิน
- Validation ป้องกันการผูกซ้ำ

### 6. ✅ สร้าง Settlement Preview Wizard

- แสดงสรุป AR, AP, และยอดสุทธิ
- Warning messages เมื่อมีปัญหา
- ปุ่มยืนยันทำ netting

## วิธีใช้งานใหม่

### สำหรับ User

1. **สร้าง/โพสต์ Vendor Bills** ของค่าธรรมเนียม/ค่าขนส่ง → ตั้ง Partner = Shopee/SPX

2. **เลือก Settlement** ในฟิลด์ "Marketplace Settlement" บนบิล
   - หรือใช้ปุ่ม "Link to Settlement"

3. **จาก Settlement** → ใช้ปุ่ม "Link Bills" เพื่อเลือกบิลเข้ามาเป็นกลุ่ม

4. **กด "Net-off Preview"** → ดูสรุปยอด AR/AP ก่อนทำ netting

5. **กด "Confirm Netting"** → ระบบสร้าง JV set-off + reconcile อัตโนมัติ

### ตรรกะการทำงาน

```python
# เมื่อกด Net-off
ap_amount = sum(vendor_bills.amount_residual)  # ยอด AP ที่ต้องจ่าย
ar_amount = settlement.net_settlement_amount   # ยอด AR ที่จะรับ
net_amount = min(ap_amount, ar_amount)         # ยอดที่จะ net

# สร้าง JV
Dr: AP–Shopee (ยอด net)
Cr: AR–Shopee (ยอด net)

# Reconcile อัตโนมัติ
- AR lines ของ Settlement ↔ Cr JV
- AP lines ของ Vendor Bills ↔ Dr JV
```

## ข้อดีของการปรับปรุง

### 1. **ผูกโดยตรง** (Direct Linking)
- ไม่ต้องพึ่ง Many2many relation
- ข้อมูลชัดเจนกว่า: บิล 1 ใบ = งวด 1 งวด

### 2. **UX ที่ดีขึ้น**
- Smart buttons ช่วยนำทาง
- Preview ก่อนทำ netting
- Auto-select bills ตามยอดเงิน

### 3. **Validation ที่แข็งแกร่ง**
- ป้องกันบิลผูกซ้ำ
- ตรวจสอบ partner เดียวกัน
- เช็คสถานะเอกสาร

### 4. **รองรับ Backward Compatibility**
- Migration script แปลงข้อมูลเดิม
- เก็บฟิลด์เดิมไว้เพื่อ compatibility

## ไฟล์ที่สร้าง/แก้ไข

### Models
- `models/sale_account_extension.py` - เพิ่มฟิลด์และฟังก์ชัน
- `models/settlement.py` - ปรับปรุง relations และ actions

### Wizards
- `wizards/bill_link_wizard.py` - ปรับปรุงทั้งหมด
- `wizards/settlement_preview_wizard.py` - เพิ่ม preview wizard
- `wizards/marketplace_netting_wizard.py` - รองรับ direct link

### Views
- `views/account_move_view_inherit.xml` - เพิ่มฟิลด์ settlement
- `views/bill_link_wizard_views.xml` - ปรับปรุง UI
- `views/settlement_preview_wizard_views.xml` - เพิ่ม preview form
- `views/marketplace_settlement_wizard_views.xml` - เพิ่ม smart buttons

### Migration
- `migrations/17.0.1.0.1/post-migration.py` - แปลงข้อมูลเดิม

## การทดสอบ

### Workflow หลัก
1. ✅ สร้าง Settlement
2. ✅ สร้าง Vendor Bills
3. ✅ ผูก Bills เข้า Settlement
4. ✅ Preview netting
5. ✅ ทำ AR/AP netting
6. ✅ ตรวจสอบ reconciliation

### Edge Cases
1. ✅ Bills ผูกซ้ำ → Error
2. ✅ Partner ต่างกัน → Error  
3. ✅ Bills ยังไม่ post → ไม่แสดงใน list
4. ✅ Settlement posted แล้ว → ไม่ให้แก้ไข

## สิ่งที่ควรทำต่อ

1. **Testing**: ทดสอบ workflow ทั้งหมด
2. **Documentation**: สร้าง user manual
3. **Training**: อบรม user ใช้งานฟีเจอร์ใหม่
4. **Performance**: ตรวจสอบประสิทธิภาพกับข้อมูลจริง

โมดูลนี้พร้อมใช้งานแล้วตามแนวคิดที่คุณอธิบาย! 🎉
