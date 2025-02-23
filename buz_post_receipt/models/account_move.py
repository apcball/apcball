from odoo import models, fields, api

class AccountMove(models.Model):
    _inherit = 'account.move'

    receipt_number = fields.Char(string='Receipt Number', readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('move_type') == 'out_invoice' and not vals.get('receipt_number'):
                vals['receipt_number'] = self.env['ir.sequence'].next_by_code('post.receipt.number') or '/'
        return super().create(vals_list)

    def action_print_post_receipt(self):
        self.ensure_one()
        return self.env.ref('buz_post_receipt.action_report_post_receipt').report_action(self)

    def amount_to_text_thai(self, amount):
        """Convert amount to Thai text"""
        def _to_thai_text(number):
            thai_number = ["ศูนย์", "หนึ่ง", "สอง", "สาม", "สี่", "ห้า", "หก", "เจ็ด", "แปด", "เก้า"]
            thai_unit = ["", "สิบ", "ร้อย", "พัน", "หมื่น", "แสน", "ล้าน"]
            
            if number == 0:
                return thai_number[0]
                
            result = ""
            unit = 0
            for i in str(number)[::-1]:
                n = int(i)
                if n != 0:
                    if unit == 0 and n == 1:
                        result = "เอ็ด" + result
                    elif unit == 1 and n == 2:
                        result = "ยี่" + thai_unit[unit] + result
                    elif unit == 1 and n == 1:
                        result = thai_unit[unit] + result
                    else:
                        result = thai_number[n] + thai_unit[unit] + result
                unit += 1
                if unit == 7:
                    unit = 1
            return result

        # แยกจำนวนเต็มและทศนิยม
        amount_int = int(amount)
        amount_dec = int(round((amount - amount_int) * 100))

        # แปลงเป็นข้อความ
        result = _to_thai_text(amount_int) + "บาท"
        if amount_dec > 0:
            result += _to_thai_text(amount_dec) + "สตางค์"
        else:
            result += "ถ้วน"

        return result

    def get_amount_with_tax(self):
        """Calculate amount with tax deduction"""
        self.ensure_one()
        amount_total = self.amount_total
        tax_deduction = amount_total * 0.03  # 3% tax deduction
        net_amount = amount_total - tax_deduction
        return {
            'amount_total': amount_total,
            'tax_deduction': tax_deduction,
            'net_amount': net_amount,
            'amount_in_words': self.amount_to_text_thai(net_amount)
        }