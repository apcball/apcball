# WHT Auto Fill Fix - สำหรับแก้ปัญหา WHT ไม่ auto fill และไม่หักตอน payment

## ปัญหาที่พบ

1. **WHT ไม่ auto fill** ใน payment register wizard
2. **ไม่มีการหัก WHT** ตอนทำ payment
3. **Writeoff fields ไม่ถูกตั้งค่า** อัตโนมัติ

## สาเหตุหลัก

### 1. Invoice Line ไม่มี WHT Tax
```
❌ Product ไม่ได้ตั้งค่า WHT Tax
❌ Invoice line ไม่มี wht_tax_id
❌ ระบบจึงไม่สามารถคำนวณ WHT ได้
```

### 2. Payment Register Wizard ไม่ทำงาน
```
❌ Context หรือ active_ids ไม่ถูกต้อง
❌ _compute_amount method ไม่ทำงาน
❌ WHT calculation logic ไม่ถูกเรียก
```

### 3. Writeoff Configuration หายไป
```
❌ payment_difference_handling ไม่เป็น "reconcile"
❌ writeoff_account_id ไม่ถูกตั้งค่า
❌ writeoff_label ไม่มีข้อมูล
```

## วิธีแก้ไขแบบละเอียด

### Fix 1: ตรวจสอบ Product Configuration

#### ขั้นตอนตรวจสอบ:
```python
# ใน Odoo shell
product = env['product.template'].search([('name', 'ilike', 'your_product')])
print(f"Product: {product.name}")
print(f"Supplier WHT Tax: {product.supplier_wht_tax_id.name if product.supplier_wht_tax_id else 'None'}")
print(f"Supplier Company WHT Tax: {product.supplier_company_wht_tax_id.name if product.supplier_company_wht_tax_id else 'None'}")
```

#### การแก้ไข:
```
1. ไปที่ Products > [เลือก Product]
2. ใน Purchase tab ตั้งค่า:
   - Supplier Individual WHT Tax: [สำหรับ vendor บุคคลธรรมดา]
   - Supplier Company WHT Tax: [สำหรับ vendor นิติบุคคล]
3. Save product
```

### Fix 2: ตรวจสอบ Invoice Line WHT

#### ขั้นตอนตรวจสอบ:
```python
# ใน Invoice form
invoice = env['account.move'].browse(INVOICE_ID)
for line in invoice.line_ids:
    if line.product_id:
        print(f"Line: {line.name}")
        print(f"Product: {line.product_id.name}")
        print(f"WHT Tax: {line.wht_tax_id.name if line.wht_tax_id else 'None'}")
```

#### การแก้ไข Manual:
```
1. เปิด Invoice ที่ต้องการ
2. ใน Invoice Line tabs:
   - คลิกแก้ไข line
   - ตั้งค่า WHT field ให้ถูกต้อง
   - Save line
3. ตรวจสอบว่า WHT amount คำนวณถูกต้อง
```

### Fix 3: Enhanced Payment Register for WHT

#### สร้าง Enhanced Method:
```python
@api.onchange('line_ids')
def _onchange_line_ids_wht(self):
    """Enhanced onchange to auto-fill WHT in payment register"""
    if self.env.context.get('active_model') == 'account.move':
        active_ids = self.env.context.get('active_ids', [])
        invoices = self.env['account.move'].browse(active_ids)
        
        # Check for WHT lines
        wht_lines = invoices.mapped('line_ids').filtered('wht_tax_id')
        if wht_lines:
            # Force recalculate WHT
            self._compute_amount()
```

### Fix 4: Manual Payment with WHT

#### วิธีทำ Payment แบบ Manual WHT:
```
1. สร้าง Payment ปกติ
2. ใน Payment Register Wizard:
   - Payment Difference Handling: "Keep open"
   - หรือเลือก "Reconcile Difference"
   
3. ตั้งค่า Writeoff:
   - Writeoff Account: เลือก WHT Payable Account
   - Writeoff Label: "WHT 3%" (หรือตามเปอร์เซ็นต์)
   - Amount: คำนวณ WHT manually
   
4. แก้ไข Payment Amount:
   - ลด Payment Amount ตาม WHT ที่หัก
   - เช่น: 10,000 - 300 = 9,700
```

## Code Fix สำหรับ Auto WHT

### Enhanced _compute_amount Method:
```python
@api.depends('source_amount', 'currency_id', 'payment_date')
def _compute_amount(self):
    """Enhanced compute amount with better WHT detection"""
    res = super()._compute_amount()
    
    # Enhanced WHT calculation
    if self.env.context.get('active_model') == 'account.move':
        active_ids = self.env.context.get('active_ids', [])
        if active_ids:
            invoices = self.env['account.move'].browse(active_ids).exists()
            
            # Get all WHT lines from invoices
            wht_lines = []
            for invoice in invoices:
                for line in invoice.line_ids:
                    if line.wht_tax_id and line.balance != 0:
                        wht_lines.append(line)
            
            if wht_lines:
                # Calculate total WHT
                total_wht_base = 0
                total_wht_amount = 0
                wht_taxes = []
                
                for line in wht_lines:
                    # Get WHT base amount
                    base_amount = abs(line.balance)
                    wht_amount = base_amount * (line.wht_tax_id.amount / 100)
                    
                    total_wht_base += base_amount
                    total_wht_amount += wht_amount
                    wht_taxes.append(line.wht_tax_id)
                
                # Apply WHT if found
                if total_wht_amount > 0:
                    self.amount -= total_wht_amount
                    self.wht_amount_base = total_wht_base
                    
                    # Set writeoff fields
                    if len(set(wht_taxes)) == 1:  # Same WHT tax
                        wht_tax = wht_taxes[0]
                        self.wht_tax_id = wht_tax
                        self.writeoff_account_id = wht_tax.account_id
                        self.writeoff_label = wht_tax.display_name
                        self.payment_difference_handling = 'reconcile'
    
    return res
```

## การทดสอบการแก้ไข

### Test Case 1: ตรวจสอบ WHT Auto Fill
```python
# สร้าง Invoice พร้อม WHT
invoice = env['account.move'].create({
    'move_type': 'in_invoice',
    'partner_id': vendor_id,
    'invoice_line_ids': [(0, 0, {
        'product_id': product_with_wht_id,
        'quantity': 1,
        'price_unit': 10000,
    })]
})
invoice.action_post()

# ทดสอบ Payment Register
with Form(env['account.payment.register'].with_context(
    active_model='account.move',
    active_ids=[invoice.id]
)) as payment_form:
    # ตรวจสอบว่า amount ลดลงตาม WHT หรือไม่
    print(f"Original amount: 10000")
    print(f"Payment amount: {payment_form.amount}")  # ควรเป็น 9700
    print(f"WHT amount: {payment_form.wht_amount_base * 0.03}")  # ควรเป็น 300
```

### Test Case 2: Manual Payment Test
```
1. สร้าง Invoice: 10,000 บาท
2. Product มี WHT 3%
3. ทำ Payment Register:
   - ตรวจสอบ amount = 9,700
   - ตรวจสอบ writeoff = 300
   - ตรวจสอบ writeoff account = WHT Payable
4. Confirm Payment
5. ตรวจสอบ Journal Entry
```

## Quick Fix Commands

### ถ้า WHT ยังไม่ทำงาน ให้รันคำสั่งนี้:

```python
# ใน Odoo shell - Force update product WHT configuration
products = env['product.template'].search([('can_be_purchased', '=', True)])
wht_tax = env['account.withholding.tax'].search([('name', 'ilike', 'service')], limit=1)

for product in products:
    if not product.supplier_company_wht_tax_id:
        product.supplier_company_wht_tax_id = wht_tax.id
        print(f"Updated {product.name}")
```

```python
# ตรวจสอบ Invoice lines และอัปเดต WHT
invoice_id = INVOICE_ID  # ใส่ ID ของ Invoice
invoice = env['account.move'].browse(invoice_id)

for line in invoice.line_ids:
    if line.product_id and not line.wht_tax_id:
        partner = invoice.partner_id
        if partner.company_type == 'company':
            line.wht_tax_id = line.product_id.supplier_company_wht_tax_id
        else:
            line.wht_tax_id = line.product_id.supplier_wht_tax_id
        print(f"Updated line: {line.name}")
```

## สรุปขั้นตอนแก้ไข

1. ✅ **ตรวจสอบ Product WHT Configuration**
2. ✅ **ตรวจสอบ Invoice Line WHT Tax**  
3. ✅ **ทดสอบ Payment Register Auto Fill**
4. ✅ **ทำ Manual Payment หาก Auto ไม่ทำงาน**
5. ✅ **ตรวจสอบ Journal Entry ที่ถูกสร้าง**

หากยังไม่ทำงาน แสดงว่าต้องการ custom code เพิ่มเติมในส่วน payment register wizard!
