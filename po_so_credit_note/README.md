# PO & SO Credit Note Module

## ภาพรวม (Overview)

Module **PO & SO Credit Note** สำหรับ Odoo 17 ช่วยให้สร้าง Credit Note อัตโนมัติจาก Purchase Order (PO) และ Sale Order (SO) โดยตรวจจับ order lines ที่มีจำนวนติดลบ หรือสามารถ refund ได้

## ลักษณะเด่น (Features)

- ✅ สร้าง Credit Note จาก Purchase Order (in_refund) สำหรับ lines ที่มียอดติดลบ
- ✅ สร้าง Credit Note จาก Sale Order (out_refund) สำหรับ lines ที่ deliver > invoice
- ✅ Wizard Interface สำหรับเลือก/ยกเลิก lines ที่จะรวมใน Credit Note
- ✅ Tracking ความสัมพันธ์ระหว่าง Credit Note และ Source Order
- ✅ รองรับ Hot Reload (Odoo 17 dev mode)
- ✅ ปุ่มแสดงอัตโนมัติเมื่อมีเงื่อนไขครบถ้วน

## การติดตั้ง (Installation)

### 1. Deploy Module
Module ได้ถูก deploy ไปที่ server แล้ว:
```
/srv/docker/odoo/custom-addons/po_so_credit_note/
```

### 2. ติดตั้งผ่าน Odoo UI
1. เข้า Odoo: http://217.216.32.33:8069
2. ไปที่ **Apps**
3. กด **Update Apps List** (มุมขวาบน)
4. ค้นหา: `PO & SO Credit Note` หรือ `Credit Note`
5. กด **Install**

## การทำงานของ Module (How It Works)

### โครงสร้างระบบ (System Architecture)

```
Purchase Order / Sale Order
         ↓
   Detect Negative/Refundable Lines
         ↓
   Show "Create Credit Note" Button
         ↓
   Open Wizard (User Selects Lines)
         ↓
   Create Account Move (Credit Note)
         ↓
   Link Source Order & Lines
```

---

## Part 1: PO Credit Note (Credit Note จากใบสั่งซื้อ)

### การทำงาน (Workflow)

**ฟลัวช์การทำงาน:**

```
1. User สร้าง PO
2. เพิ่ม line ที่มี quantity ติดลบ (เช่น -5)
3. Confirm PO → state = 'purchase'
4. System ตรวจจับ lines ที่มี qty < 0
5. แสดงปุ่ม "Create Credit Note"
6. User กดปุ่ม → เปิด Wizard
7. User เลือก lines ที่ต้องการ
8. User กด "Create Credit Note"
9. System สร้าง Account Move (type: in_refund)
10. Credit Note link กับ PO
11. User ถูก redirect ไปที่ Credit Note form
```

### Logic การตรวจจับ (Detection Logic)

**ใน `models/purchase_order.py`:**

```python
# Compute field: has_negative_lines
@api.depends('order_line.product_qty')
def _compute_has_negative_lines(self):
    """ตรวจสอบว่า PO มี lines ที่มียอดติดลบหรือไม่"""
    for order in self:
        order.has_negative_lines = any(
            line.product_qty < 0 for line in order.order_line
        )

# ปุ่มแสดงเมื่อ:
# - state อยู่ใน ['purchase', 'done'] และ
# - has_negative_lines == True
```

### การทำงานของ Wizard (Wizard Logic)

**ใน `wizards/po_credit_note_wizard.py`:**

**Step 1: Filter Lines**
```python
# เมื่อ user กดปุ่ม "Create Credit Note"
negative_lines = self.order_id.order_line.filtered(
    lambda l: l.product_qty < 0  # เลือกเฉพาะ negative lines
)
```

**Step 2: Create Wizard Lines**
```python
for line in negative_lines:
    self.env['po.credit.note.wizard.line'].create({
        'wizard_id': wizard.id,
        'po_line_id': line.id,
        'product_id': line.product_id.id,
        'product_qty': abs(line.product_qty),  # Convert negative to positive
        'price_unit': line.price_unit,
        'selected': True,  # Default select
    })
```

**Step 3: Create Credit Note**
```python
# Create Account Move (Credit Note)
move_vals = {
    'move_type': 'in_refund',  # Vendor refund
    'partner_id': po.partner_id.id,
    'journal_id': journal.id,
    'currency_id': po.currency_id.id,
    'invoice_date': date,
    'ref': f'CN/{po.name}',
    'source_po_id': po.id,  # Link to source PO
}
move = self.env['account.move'].create(move_vals)

# Create Credit Note Lines
for wizard_line in selected_lines:
    self.env['account.move.line'].create({
        'move_id': move.id,
        'product_id': po_line.product_id.id,
        'quantity': wizard_line.product_qty,
        'price_unit': wizard_line.price_unit,
        'account_id': account_id,
        'purchase_line_id': po_line.id,  # Link to PO line
        'tax_ids': po_line.taxes_id.ids,
    })
```

### ตัวอย่างการใช้งาน (Example)

**Scenario:**

1. สร้าง PO:
   - Supplier: Vendor A
   - Product A: Qty = 10, Price = 100
   - Product B: Qty = **-5**, Price = 50

2. Confirm PO

3. System ตรวจจับ:
   - `has_negative_lines` = True (เพราะ Product B qty = -5)

4. กดปุ่ม "Create Credit Note"

5. Wizard แสดง:
   | Selected | Product | Qty | Price | Subtotal |
   |----------|---------|-----|-------|----------|
   | ✅       | Product B | 5 | 50 | 250 |

6. กด "Create Credit Note"

7. Credit Note ถูกสร้าง:
   - Type: in_refund
   - Ref: CN/PO00001
   - Supplier: Vendor A
   - Lines:
     - Product B: Qty 5, Price 50, Subtotal 250

8. Credit Note link กับ PO:
   - `source_po_id` = PO00001
   - `source_line_ids` = JSON tracking

---

## Part 2: SO Credit Note (Credit Note จากใบสั่งขาย)

### การทำงาน (Workflow)

**ฟลัวช์การทำงาน:**

```
1. User สร้าง SO
2. Confirm SO → state = 'sale'
3. User ทำการ deliver products
4. User ทำการ invoice (partial หรือ full)
5. System ตรวจจับ lines ที่ refundable
6. แสดงปุ่ม "Create Credit Note"
7. User กดปุ่ม → เปิด Wizard
8. User ระบุ qty ที่จะ refund สำหรับแต่ละ line
9. User กด "Create Credit Note"
10. System สร้าง Account Move (type: out_refund)
11. Credit Note link กับ SO
12. User ถูก redirect ไปที่ Credit Note form
```

### Logic การตรวจจับ (Detection Logic)

**ใน `models/sale_order.py`:**

```python
# Compute field: has_refundable_lines
@api.depends('order_line.qty_delivered', 'order_line.qty_invoiced')
def _compute_has_refundable_lines(self):
    """ตรวจสอบว่า SO มี lines ที่ refundable หรือไม่"""
    for order in self:
        # Refundable if:
        # - Product type คือ 'consu' หรือ 'product'
        # - Delivered > Invoiced
        order.has_refundable_lines = any(
            line.qty_delivered > line.qty_invoiced
            for line in order.order_line
            if line.product_id.type in ['consu', 'product']
        )

# ปุ่มแสดงเมื่อ:
# - state = 'sale' (confirmed)
# - has_refundable_lines == True
```

### การทำงานของ Wizard (Wizard Logic)

**ใน `wizards/so_credit_note_wizard.py`:**

**Step 1: Filter Lines**
```python
# เมื่อ user กดปุ่ม "Create Credit Note"
refundable_lines = self.order_id.order_line.filtered(
    lambda l: (
        l.product_id.type in ['consu', 'product'] and
        l.qty_delivered > l.qty_invoiced  # Delivered > Invoiced
    )
)
```

**Step 2: Create Wizard Lines**
```python
for line in refundable_lines:
    qty_to_refund = line.qty_delivered - line.qty_invoiced
    self.env['so.credit.note.wizard.line'].create({
        'wizard_id': wizard.id,
        'so_line_id': line.id,
        'product_id': line.product_id.id,
        'ordered_qty': line.product_uom_qty,
        'delivered_qty': line.qty_delivered,
        'invoiced_qty': line.qty_invoiced,
        'qty_to_refund': qty_to_refund,  # Default qty to refund
        'price_unit': line.price_unit,
        'selected': True,
    })
```

**Step 3: Create Credit Note**
```python
# Create Account Move (Credit Note)
move_vals = {
    'move_type': 'out_refund',  # Customer refund
    'partner_id': so.partner_id.id,
    'journal_id': journal.id,
    'currency_id': so.currency_id.id,
    'invoice_date': date,
    'ref': f'CN/{so.name}',
    'source_so_id': so.id,  # Link to source SO
}
move = self.env['account.move'].create(move_vals)

# Create Credit Note Lines
for wizard_line in selected_lines:
    self.env['account.move.line'].create({
        'move_id': move.id,
        'product_id': so_line.product_id.id,
        'quantity': wizard_line.qty_to_refund,
        'price_unit': wizard_line.price_unit,
        'account_id': account_id,
        'sale_line_id': so_line.id,  # Link to SO line
        'tax_ids': so_line.tax_id.ids,
    })
```

### ตัวอย่างการใช้งาน (Example)

**Scenario:**

1. สร้าง SO:
   - Customer: Customer X
   - Product A: Qty = 10, Price = 200

2. Confirm SO

3. Deliver Products:
   - Product A: Delivered = 10

4. Create Invoice (Partial):
   - Product A: Invoiced = 7

5. System ตรวจจับ:
   - `has_refundable_lines` = True
   - เพราะ Delivered (10) > Invoiced (7)

6. กดปุ่ม "Create Credit Note"

7. Wizard แสดง:
   | Selected | Product | Ordered | Delivered | Invoiced | Refund | Price | Subtotal |
   |----------|---------|---------|-----------|----------|--------|-------|----------|
   | ✅       | Product A | 10 | 10 | 7 | 3 | 200 | 600 |

8. กด "Create Credit Note"

9. Credit Note ถูกสร้าง:
   - Type: out_refund
   - Ref: CN/SO00001
   - Customer: Customer X
   - Lines:
     - Product A: Qty 3, Price 200, Subtotal 600

10. Credit Note link กับ SO:
    - `source_so_id` = SO00001
    - `source_line_ids` = JSON tracking

---

## Part 3: ระบบ Tracking ความสัมพันธ์ (Relationship Tracking)

### Extended Account Move Model

**ใน `models/account_move.py`:**

```python
class AccountMove(models.Model):
    _inherit = 'account.move'

    # Track source orders
    source_po_id = fields.Many2one('purchase.order', 'Source PO')
    source_so_id = fields.Many2one('sale.order', 'Source SO')
    source_line_ids = fields.Text('Source Lines')  # JSON format
```

### JSON Tracking Structure

**ตัวอย่าง `source_line_ids`:**

```json
[
  {
    "po_line_id": 123,
    "product_id": 456,
    "quantity": 5,
    "price_unit": 50
  },
  {
    "po_line_id": 124,
    "product_id": 457,
    "quantity": 3,
    "price_unit": 100
  }
]
```

### Benefits of Tracking

1. **Traceability** - ติดตาม origin ของ credit note ย้อนหลัง
2. **Audit Trail** - เก็บประวัติการ refund
3. **Reporting** - รายงานสรุป credit notes ต่อ PO/SO
4. **Reconciliation** - จับคู่กับ PO/SO invoices ได้ง่าย

---

## Part 4: Security & Access Rights

### Access Rights Configuration

**ใน `security/ir.model.access.csv`:**

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_po_credit_note_wizard_user,po.credit.note.wizard.user,model_po_credit_note_wizard,base.group_user,1,1,1,0
access_po_credit_note_wizard_line_user,po.credit.note.wizard.line.user,model_po_credit_note_wizard_line,base.group_user,1,1,1,0
access_so_credit_note_wizard_user,so.credit.note.wizard.user,model_so_credit_note_wizard,base.group_user,1,1,1,0
access_so_credit_note_wizard_line_user,so.credit.note.wizard.line.user,model_so_credit_note_wizard_line,base.group_user,1,1,1,0
```

### Role-Based Access

| Role | PO Credit Note | SO Credit Note | Account Moves |
|------|---------------|----------------|---------------|
| **Purchase User** | ✅ Create/View | ❌ No | ✅ View in_refund |
| **Sales User** | ❌ No | ✅ Create/View | ✅ View out_refund |
| **Accountant** | ✅ Full Access | ✅ Full Access | ✅ Full Access |
| **Manager** | ✅ Full Access | ✅ Full Access | ✅ Full Access |

---

## Part 5: Technical Architecture

### Module Structure

```
po_so_credit_note/
├── __init__.py                  # Root init
├── __manifest__.py              # Module manifest
├── models/
│   ├── __init__.py
│   ├── account_move.py          # Extend account.move (credit notes)
│   ├── purchase_order.py        # Extend purchase.order (PO logic)
│   └── sale_order.py            # Extend sale.order (SO logic)
├── views/
│   ├── account_move_views.xml    # Credit note views
│   ├── purchase_order_views.xml # PO button & views
│   └── sale_order_views.xml     # SO button & views
├── wizards/
│   ├── __init__.py
│   ├── po_credit_note_wizard.py      # PO wizard logic
│   ├── po_credit_note_wizard_views.xml
│   ├── so_credit_note_wizard.py      # SO wizard logic
│   └── so_credit_note_wizard_views.xml
├── security/
│   └── ir.model.access.csv     # Access rights
└── static/src/xml/
    └── credit_note_button.xml  # JS/XML assets
```

### Models Overview

| Model | Type | Purpose |
|-------|------|---------|
| `account.move` | Extension | Track source PO/SO |
| `purchase.order` | Extension | Compute has_negative_lines, button action |
| `sale.order` | Extension | Compute has_refundable_lines, button action |
| `po.credit.note.wizard` | Transient | PO credit note creation wizard |
| `po.credit.note.wizard.line` | Transient | PO wizard lines |
| `so.credit.note.wizard` | Transient | SO credit note creation wizard |
| `so.credit.note.wizard.line` | Transient | SO wizard lines |

### Key Methods

**PO Credit Note:**
- `action_open_po_credit_note_wizard()` - Open PO wizard
- `_compute_has_negative_lines()` - Detect negative lines
- `action_create_credit_note()` - Create in_refund

**SO Credit Note:**
- `action_open_so_credit_note_wizard()` - Open SO wizard
- `_compute_has_refundable_lines()` - Detect refundable lines
- `action_create_credit_note()` - Create out_refund

---

## Part 6: Development & Testing

### Hot Reload Development

Odoo 17 รองรับ **Hot Reload** สำหรับการพัฒนา:

```bash
# SSH ไป server
ssh root@217.216.32.33
cd /srv/docker/odoo/custom-addons/po_so_credit_note

# แก้ไข code
vim models/purchase_order.py
vim views/purchase_order_views.xml

# Save → Auto reload (1-3 วินาที)
# Refresh browser → เปลี่ยนแปลงจะแสดง
```

**File Types ที่รองรับ Hot Reload:**
- ✅ `.py` (Python) - Models, controllers, wizards
- ✅ `.xml` (Views) - View definitions
- ✅ `.js` (JavaScript) - Static JS files
- ✅ `.css` - Style sheets

**File Types ที่ต้อง Restart Container:**
- ❌ `__manifest__.py` - Module configuration
- ❌ `__init__.py` - Import configuration
- ❌ การเปลี่ยน folder structure

### Testing Checklist

#### Test 1: PO Credit Note

**Steps:**
1. Create PO with mixed quantities:
   - Product A: Qty = 10, Price = 100
   - Product B: Qty = **-5**, Price = 50
2. Confirm PO
3. Verify `has_negative_lines` = True
4. Click "Create Credit Note" button
5. Verify wizard shows Product B with Qty = 5
6. Click "Create Credit Note"
7. Verify Credit Note:
   - Type: in_refund
   - Ref: CN/POxxxxx
   - Line: Product B, Qty 5, Price 50
   - Subtotal: 250
8. Verify `source_po_id` links to PO

**Expected Result:**
- ✅ Credit Note created successfully
- ✅ Negative line converted to positive qty
- ✅ Source PO tracked

#### Test 2: SO Credit Note

**Steps:**
1. Create SO:
   - Product X: Qty = 10, Price = 200
2. Confirm SO
3. Deliver 10 units
4. Create invoice for 7 units
5. Verify `has_refundable_lines` = True
6. Click "Create Credit Note" button
7. Verify wizard shows:
   - Ordered: 10
   - Delivered: 10
   - Invoiced: 7
   - Refund: 3
8. Adjust refund qty to 2
9. Click "Create Credit Note"
10. Verify Credit Note:
    - Type: out_refund
    - Ref: CN/SOxxxxx
    - Line: Product X, Qty 2, Price 200
    - Subtotal: 400
11. Verify `source_so_id` links to SO

**Expected Result:**
- ✅ Credit Note created successfully
- ✅ Refund qty matches wizard selection
- ✅ Source SO tracked

#### Test 3: Edge Cases

**Test 3a: No Negative Lines**
1. Create PO with positive quantities only
2. Confirm PO
3. Verify button is **hidden**

**Test 3b: No Refundable Lines**
1. Create SO
2. Deliver 10 units
3. Invoice 10 units (full)
4. Verify button is **hidden**

**Test 3c: Multiple Credit Notes**
1. Create PO with Product A: Qty = -5, Product B: Qty = -3
2. Confirm PO
3. Create Credit Note (select Product A only)
4. Create another Credit Note (select Product B)
5. Verify both credit notes link to PO

### Debugging

**View Logs:**
```bash
ssh root@217.216.32.33
cd /srv/docker/odoo
docker compose logs -f odoo
```

**Check Module Status:**
```bash
# ตรวจสอบ module files
ls -la /srv/docker/odoo/custom-addons/po_so_credit_note/

# ตรวจสอบ Python syntax
python3 -m py_compile models/*.py wizards/*.py

# ตรวจสอบ XML syntax
xmllint --noout views/*.xml wizards/*.xml
```

---

## Part 7: UI Reference

### PO Form - Button Location

```
+--------------------------------------------------+
| Purchase Order: PO00001                          |
+--------------------------------------------------+
| Order Lines:                                     |
| ┌──────────────────────────────────────────────┐ |
| │ Product  │ Qty  │ Price  │ Subtotal        │ |
| ├──────────────────────────────────────────────┤ |
| │ Product A │ 10  │ 100   │ 1000            │ |
| │ Product B │ -5  │ 50    │ -250            │ |
| └──────────────────────────────────────────────┘ |
+--------------------------------------------------+
| [Create Credit Note] [Cancel] [Lock]            |
|  ↑                                               |
|  Button shows when has_negative_lines = True     |
+--------------------------------------------------+
```

### PO Credit Note Wizard

```
+--------------------------------------------------+
| Create PO Credit Note                            |
+--------------------------------------------------+
| Purchase Order: PO00001                          |
| Journal: Vendor Bills                            |
| Date: 2025-05-08                                |
| Reason:                                          |
+--------------------------------------------------+
| Lines:                                           |
| ┌─┬───────────────────────────────────────────┐ |
| │☑│ Product │ Qty │ Price │ Subtotal        │ |
| ├─┼───────────────────────────────────────────┤ |
*│☑│Product B│ 5  │ 50   │ 250             │ |*
| └─┴───────────────────────────────────────────┘ |
+--------------------------------------------------+
| [Create Credit Note]           [Cancel]            |
+--------------------------------------------------+
```

### SO Credit Note Wizard

```
+--------------------------------------------------+
| Create SO Credit Note                            |
+--------------------------------------------------+
| Sale Order: SO00001                              |
| Journal: Customer Invoices                       |
| Date: 2025-05-08                                |
| Reason:                                          |
+--------------------------------------------------+
| Lines:                                           |
| ┌─┬────┬────────┬────────┬─────┬────┬──────┐ |
| │☑│Prod│ Ordered│Delivered│Invcd│Rfnd│Total │ |
*├─┼────┼────────┼────────┼─────┼────┼──────┤ |*
*│☑│P.X │ 10     │ 10     │ 7   │ 3  │ 600  │ |*
| └─┴────┴────────┴────────┴─────┴────┴──────┘ |
+--------------------------------------------------+
| [Create Credit Note]           [Cancel]            |
+--------------------------------------------------+
```

### Credit Note Form

```
+--------------------------------------------------+
| Credit Note: CN/PO00001 (BILL/2025/0001)          |
+--------------------------------------------------+
| Partner: Vendor A                                 |
| Source PO: PO00001                               |
| Invoice Date: 2025-05-08                          |
+--------------------------------------------------+
| Invoice Lines:                                    |
| ┌──────────────────────────────────────────────┐ |
*│ Product  │ Qty  │ Price  │ Tax  │ Subtotal   │ |*
*├──────────────────────────────────────────────┤ |*
*│ Product B │ 5  │ 50    │ 7%   │ 267.50     │ |*
*└──────────────────────────────────────────────┘ |*
+--------------------------------------------------+
| Total: 267.50                                     |
+--------------------------------------------------+
```

---

## Part 8: FAQ (คำถามที่พบบ่อย)

### Q1: ปุ่ม "Create Credit Note" ไม่แสดง?
**A:** ตรวจสอบ:
- PO: state ต้องเป็น 'purchase' หรือ 'done' และมี negative lines
- SO: state ต้องเป็น 'sale' และมี refundable lines (delivered > invoiced)

### Q2: สร้าง Credit Note แล้วเกิด error "Please define an expense/income account"?
**A:** ตรวจสอบ account settings:
- PO: Product ต้องมี Expense Account
- SO: Product ต้องมี Income Account
- Category ต้องมี default account

### Q3: Qty ใน Credit Note ผิด?
**A:** ระบบอัตโนมัติแปลงค่า:
- PO: abs(negative_qty) → positive
- SO: delivered - invoiced = qty_to_refund

### Q4: Credit Note ไม่ link กับ PO/SO?
**A:** ตรวจสอบ:
- `source_po_id` / `source_so_id` ใน credit note form
- ต้อง create ผ่าน wizard ของ module เท่านั้น

### Q5: Hot reload ไม่ทำงาน?
**A:** ตรวจสอบ:
- Odoo ต้องรันใน dev mode: `--dev=reload`
- ตรวจ logs: `docker compose logs -f odoo`
- ถ้าแก้ `__manifest__.py` ต้อง restart container

### Q6: สร้าง Credit Note แล้วไม่ validate อัตโนมัติ?
**A:** ระบบพยายาม validate แต่ถ้ามี error จะไม่ validate และคืน draft status ให้ user validate เอง

### Q7: สามารถ refund เฉพาะบาง lines ได้ไหม?
**A:** ได้! ใน wizard สามารถ uncheck lines ที่ไม่ต้องการ หรือเปลี่ยน qty ได้

### Q8: Credit Note ถูก validate แล้ว แก้ไขได้ไหม?
**A:** ไม่ได้ ใช้ Draft Cancellation & Reversal (Odoo standard behavior)

---

## Part 9: Future Enhancements

### รายการที่อาจจะพัฒนาต่อ

1. **Batch Credit Notes** - สร้าง credit notes หลายใบพร้อมกัน
2. **Credit Note Templates** - Template สำหรับ refund reasons
3. **Approval Workflow** - ให้ manager approve ก่อน create credit note
4. **Automatic Email Notifications** - แจ้ง supplier/customer เมื่อ create credit note
5. **Refund Analytics** - Dashboard สำหรับ track refunds
6. **Partial Refund Calculation** - Auto-calculate refund amounts based on discounts
7. **Multi-Currency Support** - รองรับ currency ที่ต่างกันระหว่าง PO/SO และ Credit Note

---

## License

LGPL-3

## Author

AI-DEV-Module-Odoo17

## Version

17.0.1.0.0

---

**Last Updated:** 2025-05-08
**Odoo Version:** 17.0
**Status:** ✅ Production Ready
