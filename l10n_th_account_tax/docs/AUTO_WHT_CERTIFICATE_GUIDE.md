# Auto WHT Certificate Generation Guide

## 🎯 Overview
ระบบ Auto WHT Certificate Generation ใน l10n_th_account_tax v2.0 จะสร้าง WHT Certificate อัตโนมัติเมื่อ Payment ที่มี WHT Tax ถูก post

## 🔧 How It Works

### 1. Detection Process
ระบบจะตรวจสอบ WHT Tax ใน payment ผ่าน 3 วิธี:
- **Method 1**: ตรวจสอบ field `wht_tax_id` ใน account.move.line
- **Method 2**: ตรวจสอบ tax lines ที่มี `amount < 0` (standard WHT taxes)
- **Method 3**: ตรวจสอบ invoice lines ที่มี tax_ids ที่เป็น WHT

### 2. Auto-Generation Trigger
การสร้าง WHT Certificate อัตโนมัติจะเกิดขึ้นเมื่อ:
```python
# ใน account_payment.py
def action_post(self):
    res = super().action_post()
    for payment in self:
        if payment.has_wht_tax and payment.state == 'posted':
            # Auto-generate WHT certificates
```

### 3. Certificate Creation Flow
```
Payment.action_post() 
    ↓
AccountMove._post() 
    ↓
AccountMove.auto_create_wht_cert_from_payment()
    ↓
WHT Certificate Created
```

## 📋 Implementation Details

### Key Methods

#### `account_payment.py`
- `_compute_has_wht_tax()`: ตรวจจับ WHT tax ใน payment
- `_get_wht_tax_data()`: ดึงข้อมูล WHT จาก reconciled invoices
- `action_post()`: เรียกใช้ auto-generation หลัง post payment

#### `account_move.py`
- `auto_create_wht_cert_from_payment()`: สร้าง WHT certificate อัตโนมัติ
- `_create_auto_wht_certificate()`: สร้าง certificate สำหรับ partner
- `_post()`: เรียกใช้ auto-generation เมื่อ post move

### Data Flow
```python
# 1. ดึงข้อมูล WHT จาก invoices
wht_data = payment._get_wht_tax_data()

# 2. จัดกลุ่มตาม partner
partner_wht_data = {}
for data in wht_data:
    partner_id = data['partner_id']
    if partner_id not in partner_wht_data:
        partner_wht_data[partner_id] = []
    partner_wht_data[partner_id].append(data)

# 3. สร้าง certificate สำหรับแต่ละ partner
for partner_id, partner_data in partner_wht_data.items():
    partner = self.env['res.partner'].browse(partner_id)
    cert = self._create_auto_wht_certificate(partner, partner_data)
```

## 🧪 Testing Guide

### 1. Create Test Scenario
```
1. สร้าง Vendor Bill ที่มี WHT Tax 3%
2. Confirm Bill
3. สร้าง Payment และ reconcile กับ Bill
4. Post Payment
5. ตรวจสอบว่า WHT Certificate ถูกสร้างอัตโนมัติ
```

### 2. Expected Results
- `payment.has_wht_tax` = True
- WHT Certificate ถูกสร้างใน draft state
- Certificate มี partner และ amount ถูกต้อง
- Link กลับไปยัง payment และ move

### 3. Validation Points
```python
# ตรวจสอบใน Python console
payment = self.env['account.payment'].browse(PAYMENT_ID)
print(f"Has WHT: {payment.has_wht_tax}")
print(f"WHT Cert Count: {payment.wht_cert_count}")
print(f"Certificates: {payment.wht_cert_ids.mapped('name')}")
```

## 🔧 Troubleshooting

### Common Issues

#### 1. Certificate Not Created
**Check:**
- `payment.has_wht_tax` = True?
- `payment.state` = 'posted'?
- มี reconciled invoices ที่มี WHT?

#### 2. Wrong Amount
**Check:**
- WHT tax calculation ใน invoice
- tax_totals computation
- _get_wht_tax_data() results

#### 3. Multiple Certificates
**Check:**
- Partner grouping logic
- Duplicate detection

### Debug Commands
```python
# ใน Odoo shell
payment = env['account.payment'].browse(ID)

# ตรวจสอบ WHT detection
print(payment.has_wht_tax)

# ตรวจสอบ WHT data
wht_data = payment._get_wht_tax_data()
print(wht_data)

# Manual generation
payment.action_manual_generate_wht_cert()
```

## 📈 Performance Notes

- Auto-generation ทำงานหลัง payment posting
- มี error handling เพื่อป้องกันการ crash
- ใช้ logging สำหรับ debugging
- รองรับ multiple partners ใน payment เดียว

## 🔒 Security Considerations

- ตรวจสอบ permission ก่อนสร้าง certificate
- Validate data ก่อน create record
- Error handling ป้องกันการ crash ของระบบ

## 📝 Configuration

### Default Settings
```python
# Default income tax form
cert_vals['income_tax_form'] = 'pnd3'

# Default state
cert_vals['state'] = 'draft'

# Auto-link to payment and move
cert_vals['payment_id'] = payment.id
cert_vals['move_id'] = move.id
```

---
**Version**: v2.0  
**Last Updated**: 6 สิงหาคม 2568  
**Status**: ✅ Active and Working
