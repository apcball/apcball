# Prompt Engineering – Odoo 17 Module: buz_auto_import_accounting

## 🎯 Objective
สร้างโมดูล `buz_auto_import_accounting` สำหรับลงบัญชีอัตโนมัติเมื่อของจากต่างประเทศ
ถูกโอนจากคลังพัก (TS01) → คลังจริง (RM01)  
โดยอ้างอิง Vendor ที่กำหนดใน Rule (Vendor = User Config เองได้)  
ระบบจะสร้าง Journal Entry อัตโนมัติ:

| เดบิต | เครดิต |
|--------|----------|
| ซื้อสินค้า (141102) | สินค้าระหว่างทาง (141101) |

---

## 🧱 Module Information
**Module Name:** buz_auto_import_accounting  
**Version:** 17.0.1.0.0  
**Category:** Accounting / Inventory  
**Depends:** `stock`, `account`, `stock_picking_batch`  
**License:** LGPL-3  

---

## 🧩 Functional Concept

### Step 1 – Purchase & Receipt
1. User เปิด PO หลายใบ (Vendor เดียวกัน)
2. สินค้ามาถึงประเทศ → รับเข้าคลัง TS01 (คลังพักระหว่างทาง)
3. User สร้าง Bill และชำระเงิน (Debit “สินค้าระหว่างทาง”, Credit “เจ้าหนี้ต่างประเทศ”)
4. ยังไม่บันทึกสินค้าคงคลังจริง

### Step 2 – Goods Arrive at Factory
1. เมื่อของมาถึง → User สร้างใบ Transfer (TS01 → RM01)
2. เมื่อ Validate Transfer → สร้าง Journal Entry อัตโนมัติ  
   Debit “ซื้อสินค้า”, Credit “สินค้าระหว่างทาง”
3. ใช้ได้ทั้งกรณี Transfer ปกติ หรือ Batch Transfer รวมหลาย PO

---

## ⚙️ Key Features
- ✅ Config rule ได้เองผ่านเมนู: **Auto Import Accounting Rules**
- ✅ รองรับหลาย PO / หลาย Bill ต่อ Vendor เดียวกัน  
- ✅ Auto JE เมื่อ Validate ใบ Transfer (TS01 → RM01)  
- ✅ รองรับ Batch Transfer  
- ✅ ป้องกันซ้ำ ด้วย field `auto_je_created`  
- ✅ สามารถเพิ่ม Cron Job รวบยอด JE รายวันได้ในอนาคต  

---

## 🧠 Data Model

### Model: `buz.import.account.rule`
เก็บกติกาการลงบัญชีอัตโนมัติ

| Field | Type | Description |
|--------|------|-------------|
| name | Char | Rule name |
| vendor_id | Many2one(res.partner) | Vendor ที่ต้องการลงบัญชีอัตโนมัติ |
| source_location_id | Many2one(stock.location) | คลังต้นทาง เช่น TS01 |
| dest_location_id | Many2one(stock.location) | คลังปลายทาง เช่น RM01 |
| debit_account_id | Many2one(account.account) | บัญชีเดบิต เช่น 141102 ซื้อสินค้า |
| credit_account_id | Many2one(account.account) | บัญชีเครดิต เช่น 141101 สินค้าระหว่างทาง |
| journal_id | Many2one(account.journal) | Journal ที่ใช้สร้างรายการ |
| auto_trigger | Boolean | เปิด/ปิดการทำงานอัตโนมัติ |
| note | Text | หมายเหตุเพิ่มเติม |

---

## 🧩 Core Logic

### Hook 1: `stock.picking.button_validate()`
เมื่อ User กด Validate ใบ Transfer → ตรวจสอบเงื่อนไข rule → สร้าง JE อัตโนมัติ

```python
from odoo import models, api, fields

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    auto_je_created = fields.Boolean('Auto JE Created', default=False)

    @api.model
    def button_validate(self):
        res = super().button_validate()
        for picking in self:
            rule = self.env['buz.import.account.rule'].search([
                ('vendor_id', '=', picking.partner_id.id),
                ('source_location_id', '=', picking.location_id.id),
                ('dest_location_id', '=', picking.location_dest_id.id),
                ('auto_trigger', '=', True)
            ], limit=1)

            if not rule or picking.auto_je_created:
                continue

            total_amount = sum([
                move.product_id.standard_price * move.product_uom_qty
                for move in picking.move_ids_without_package
            ])

            if total_amount:
                je_vals = {
                    'ref': f'Auto JE Import Transfer {picking.name}',
                    'journal_id': rule.journal_id.id,
                    'line_ids': [
                        (0, 0, {
                            'name': f'ซื้อสินค้า ({picking.partner_id.name})',
                            'account_id': rule.debit_account_id.id,
                            'debit': total_amount,
                            'credit': 0.0,
                        }),
                        (0, 0, {
                            'name': f'สินค้าระหว่างทาง ({picking.partner_id.name})',
                            'account_id': rule.credit_account_id.id,
                            'credit': total_amount,
                            'debit': 0.0,
                        }),
                    ]
                }
                self.env['account.move'].create(je_vals)
                picking.auto_je_created = True
        return res
🧾 Menu & Views

Menu: Inventory → Configuration → Auto Import Accounting Rules

Model: buz.import.account.rule

View: tree + form

Access: Accounting & Inventory Managers

🔒 Security

security/ir.model.access.csv

id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_buz_import_account_rule,buz.import.account.rule,model_buz_import_account_rule,,1,1,1,1

🚀 Summary

เมื่อของจากต่างประเทศถูกโอนจากคลังพัก (TS01) → คลังจริง (RM01)
ระบบจะตรวจจับ Vendor + Location ตาม Rule ที่ตั้งไว้ แล้วสร้าง Journal Entry ให้อัตโนมัติ
รองรับทั้ง Single Transfer และ Batch Transfer

💚 Expected Outcome

ผู้ใช้งานไม่ต้องสร้าง JE เองอีกต่อไป

บัญชี “สินค้าระหว่างทาง” จะถูกตัดอัตโนมัติเมื่อของถึงโรงงาน

Flow นำเข้ามีความถูกต้อง + ปิดบัญชีได้สมบูรณ์



