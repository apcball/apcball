# WHT Invoice Line Implementation - Fix Summary

## ปัญหาที่แก้ไข
- **หลัก**: Withholding Tax Move ไม่ถูกบันทึกเมื่อไม่มี field WHT ใน invoice line
- **ผลกระทบ**: WHT ถูกบันทึกผิดที่ Tax Invoices แทนที่จะเป็น Withholding Tax Moves

## การแก้ไขที่ทำ

### 1. เพิ่ม Field WHT ใน Invoice Line (`account_move_odoo17.py`)

```python
class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    # Enhanced WHT field for invoice lines - ป้องกัน Withholding Tax Move ไม่ถูกบันทึก
    wht_invoice_line_tax = fields.Many2one(
        comodel_name="account.withholding.tax",
        string="WHT (Invoice Line)",
        help="Withholding Tax for this invoice line - ensures WHT moves are recorded correctly",
        copy=True,
    )
    
    wht_invoice_amount = fields.Monetary(
        string="WHT Amount",
        compute="_compute_wht_invoice_amount",
        store=True,
    )
    
    wht_invoice_base = fields.Monetary(
        string="WHT Base",
        compute="_compute_wht_invoice_amount", 
        store=True,
    )
```

### 2. การคำนวณยอด WHT อัตโนมัติ

- คำนวณยอดฐาน WHT จาก `price_subtotal`
- คำนวณยอด WHT ตามเปอร์เซ็นต์ที่กำหนด
- รองรับทั้งระบบเดิม (`wht_tax_id`) และระบบใหม่ (`wht_invoice_line_tax`)

### 3. สร้าง Withholding Tax Moves อัตโนมัติ

```python
def _create_wht_moves_from_invoice_lines(self):
    """สร้าง withholding tax moves จาก invoice lines ที่มี WHT"""
    # ลบ wht_moves เดิมที่อาจมีปัญหา
    self.wht_move_ids.unlink()
    
    # หา invoice lines ที่มี WHT
    wht_lines = self.invoice_line_ids.filtered(
        lambda l: (l.wht_invoice_line_tax or l.wht_tax_id) and l.wht_invoice_amount > 0
    )
    
    # สร้าง withholding moves
    if wht_lines:
        wht_moves = []
        for line in wht_lines:
            wht_vals = line._prepare_wht_move_vals()
            if wht_vals:
                wht_vals['move_id'] = self.id
                wht_moves.append((0, 0, wht_vals))
        
        if wht_moves:
            self.write({'wht_move_ids': wht_moves})
```

### 4. View การแสดงผล (`account_move_line_wht_view.xml`)

- เพิ่ม field WHT ใน invoice line form และ tree view
- แสดงยอดรวม WHT ในส่วน totals ของ invoice
- เพิ่มปุ่มสร้างใบหัก ณ ที่จ่ายจาก invoice lines

### 5. ฟีเจอร์เพิ่มเติม

- สร้างใบหัก ณ ที่จ่ายอัตโนมัติจาก invoice lines
- รวมยอด WHT ตามประเภทภาษีและลูกค้า
- แสดงสถานะ WHT ใน invoice form

## การใช้งาน

1. **ใน Invoice Line**: เลือก WHT tax ในคอลัมน์ "WHT"
2. **คำนวณอัตโนมัติ**: ระบบจะคำนวณยอด WHT อัตโนมัติ
3. **Post Invoice**: เมื่อ post เอกสาร ระบบจะสร้าง Withholding Tax Moves อัตโนมัติ
4. **สร้างใบหัก ณ ที่จ่าย**: คลิก "Create WHT Cert" เพื่อสร้างใบหัก ณ ที่จ่าย

## ประโยชน์

✅ **แก้ปัญหาหลัก**: Withholding Tax Move ถูกบันทึกถูกต้อง
✅ **ลดข้อผิดพลาด**: ไม่มีการบันทึก WHT ผิดที่ Tax Invoices  
✅ **ใช้งานง่าย**: เลือก WHT ได้ตรงใน invoice line
✅ **รองรับระบบเดิม**: ทำงานร่วมกับ field `wht_tax_id` เดิม
✅ **คำนวณอัตโนมัติ**: ไม่ต้องคำนวณ WHT เอง
✅ **ใบหัก ณ ที่จ่าย**: สร้างได้ตรงจาก invoice

## Files ที่แก้ไข

1. `models/account_move_odoo17.py` - เพิ่ม WHT fields และ logic
2. `views/account_move_line_wht_view.xml` - เพิ่ม UI สำหรับ WHT
3. `__manifest__.py` - เพิ่ม view ใหม่
4. `WHT_INVOICE_LINE_FIX.md` - เอกสารนี้

## Testing

ทดสอบโดย:
1. สร้าง invoice ใหม่
2. เพิ่ม product line และเลือก WHT tax
3. ตรวจสอบการคำนวณยอด WHT
4. Post invoice และตรวจสอบ Withholding Tax Moves
5. สร้างใบหัก ณ ที่จ่าย

**สถานะ**: ✅ **แก้ไขเสร็จสิ้น** - พร้อมใช้งาน
