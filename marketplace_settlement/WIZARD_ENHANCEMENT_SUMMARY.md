# Marketplace Settlement Wizard Enhancement Summary

## ปัญหาที่แก้ไข

1. **Settlement ถูก post ทันที**: เดิม wizard จะสร้าง settlement และ post ทันที ทำให้ไม่สามารถตรวจสอบก่อน post ได้
2. **ไม่มีการสร้าง vendor bill อัตโนมัติ**: ไม่มีตัวเลือกในการสร้าง vendor bill สำหรับ marketplace fees

## การแก้ไขที่ทำ

### 1. เพิ่มฟิลด์ใหม่ใน Wizard

```python
# Settlement posting options
auto_post_settlement = fields.Boolean('Auto Post Settlement', default=False,
                                     help='Automatically post the settlement after creation')

# Vendor Bill Creation options
create_vendor_bill = fields.Boolean('Create Vendor Bill', default=False,
                                   help='Automatically create vendor bill for marketplace fees')
vendor_partner_id = fields.Many2one('res.partner', string='Vendor Partner',
                                   help='Vendor partner for the bill (usually marketplace)')
purchase_journal_id = fields.Many2one('account.journal', string='Purchase Journal',
                                     domain="[('type', '=', 'purchase')]",
                                     help='Journal for vendor bill')
bill_reference = fields.Char('Bill Reference', help='Vendor bill reference')
bill_date = fields.Date('Bill Date', help='Vendor bill date')

# Tax configuration for vendor bill
vat_tax_id = fields.Many2one('account.tax', string='VAT Tax',
                            domain="[('type_tax_use', '=', 'purchase'), ('amount_type', '=', 'percent')]",
                            help='VAT tax for vendor bill')
wht_tax_id = fields.Many2one('account.tax', string='WHT Tax',
                            domain="[('type_tax_use', '=', 'purchase'), ('amount_type', '=', 'percent')]",
                            help='Withholding tax for vendor bill')
```

### 2. อัปเดท Logic ใน action_create()

```python
def action_create(self):
    # ... validation ...
    
    # Create settlement (always as draft first)
    settlement = self.env['marketplace.settlement'].create({...})

    # Create vendor bill if requested
    vendor_bill = None
    if self.create_vendor_bill:
        vendor_bill = self._create_vendor_bill(settlement)

    # Post settlement if auto-post is enabled
    if self.auto_post_settlement:
        try:
            action = settlement.action_create_settlement()
            if vendor_bill:
                # Link vendor bill to settlement for netting
                settlement.vendor_bill_ids = [(4, vendor_bill.id)]
        except Exception as e:
            raise UserError(_('Failed to post settlement: %s') % str(e))
    
    # Return action to open settlement form
    return {...}
```

### 3. เพิ่ม Method สำหรับสร้าง Vendor Bill

```python
def _create_vendor_bill(self, settlement):
    """Create vendor bill for marketplace fees"""
    # Prepare bill lines for marketplace fees
    bill_lines = []
    
    # Add marketplace fee line
    if self.fee_amount and self.fee_amount > 0:
        fee_line_vals = {
            'name': f'Marketplace Fee - {settlement.name}',
            'account_id': self.fee_account_id.id,
            'price_unit': self.fee_amount,
            'quantity': 1,
        }
        
        # Add taxes if configured
        tax_ids = []
        if self.vat_tax_id:
            tax_ids.append(self.vat_tax_id.id)
        if self.wht_tax_id:
            tax_ids.append(self.wht_tax_id.id)
        
        if tax_ids:
            fee_line_vals['tax_ids'] = [(6, 0, tax_ids)]
            
        bill_lines.append((0, 0, fee_line_vals))

    # Create vendor bill
    bill_vals = {
        'move_type': 'in_invoice',
        'partner_id': self.vendor_partner_id.id,
        'journal_id': self.purchase_journal_id.id,
        'invoice_date': self.bill_date,
        'ref': self.bill_reference or f'BILL-{settlement.name}',
        'narration': f'Marketplace fees for settlement {settlement.name}',
        'invoice_line_ids': bill_lines,
    }

    vendor_bill = self.env['account.move'].create(bill_vals)
    vendor_bill.settlement_ref = settlement.name
    
    return vendor_bill
```

### 4. อัปเดท Profile Integration

เพิ่มการโหลดค่า default จาก profile สำหรับ:
- `vendor_partner_id`
- `purchase_journal_id` 
- `vat_tax_id`
- `wht_tax_id`

### 5. อัปเดท View

เพิ่ม section ใหม่ใน wizard view:

```xml
<!-- Settlement Posting Options -->
<group string="Settlement Options" name="posting_options">
    <group>
        <field name="auto_post_settlement" widget="boolean_toggle"/>
    </group>
    <group>
        <div class="alert alert-info" role="alert" invisible="auto_post_settlement">
            <i class="fa fa-info-circle"/> Settlement will be created as <strong>draft</strong>. You can review and post it manually.
        </div>
        <div class="alert alert-warning" role="alert" invisible="not auto_post_settlement">
            <i class="fa fa-warning"/> Settlement will be <strong>posted immediately</strong> after creation.
        </div>
    </group>
</group>

<!-- Vendor Bill Creation Section -->
<group string="Vendor Bill Creation" name="vendor_bill_creation">
    <!-- ... vendor bill fields ... -->
</group>
```

### 6. เพิ่มฟิลด์ settlement_ref ใน account.move

```python
settlement_ref = fields.Char('Settlement Reference', help='Reference to marketplace settlement for vendor bills')
```

## ฟิลด์ที่ต้องกรอกใน Wizard สำหรับการสร้าง Bill อัตโนมัติ

### ฟิลด์บังคับ (Required):
1. **Create Vendor Bill**: เปิดใช้งานการสร้าง vendor bill
2. **Vendor Partner**: คู่ค้าผู้ขาย (มักจะเป็น marketplace เอง)
3. **Purchase Journal**: วารสารซื้อ
4. **Bill Date**: วันที่ของ bill

### ฟิลด์เสริม (Optional):
1. **Bill Reference**: เลขที่อ้างอิง (จะ auto-generate ถ้าไม่กรอก)
2. **VAT Tax**: ภาษีมูลค่าเพิ่ม
3. **WHT Tax**: ภาษีหัก ณ ที่จ่าย

### ฟิลด์ที่โหลดจาก Profile:
- **Vendor Partner**: จาก `profile.vendor_partner_id`
- **Purchase Journal**: จาก `profile.purchase_journal_id`
- **VAT Tax**: จาก `profile.vat_tax_id`
- **WHT Tax**: จาก `profile.wht_tax_id`

## การใช้งาน

1. **Draft Mode (แนะนำ)**: ปล่อย "Auto Post Settlement" ไว้เป็น False
   - Settlement จะถูกสร้างเป็น draft
   - สามารถตรวจสอบและแก้ไขได้ก่อน post
   - ถ้าสร้าง vendor bill จะสามารถ link เข้ากับ settlement สำหรับ netting ได้

2. **Auto Post Mode**: เปิด "Auto Post Settlement" 
   - Settlement จะถูก post ทันที
   - Vendor bill จะถูก link เข้ากับ settlement อัตโนมัติ

3. **การสร้าง Vendor Bill**: เปิด "Create Vendor Bill"
   - จะสร้าง vendor bill สำหรับ marketplace fee
   - สามารถใช้สำหรับ AR/AP netting ได้
   - จะมี reference กลับไปหา settlement

## ประโยชน์

1. **ความปลอดภัย**: Settlement เป็น draft ก่อน ตรวจสอบได้ก่อน post
2. **อัตโนมัติ**: สร้าง vendor bill อัตโนมัติสำหรับ marketplace fees
3. **Netting**: Vendor bill สามารถใช้สำหรับ AR/AP netting ได้
4. **การตรวจสอบ**: สามารถเชื่อมโยง vendor bill กับ settlement ได้
5. **ความยืดหยุ่น**: สามารถเลือกได้ว่าจะ post ทันทีหรือไม่
