from odoo import models, fields, api
from datetime import datetime

class AccountPayment(models.Model):
    _inherit = 'account.payment'

    def amount_in_words(self):
        def thai_number_to_text(number):
            thai_numbers = ["ศูนย์", "หนึ่ง", "สอง", "สาม", "สี่", "ห้า", "หก", "เจ็ด", "แปด", "เก้า"]
            thai_units = ["", "สิบ", "ร้อย", "พัน", "หมื่น", "แสน", "ล้าน"]

            if number == 0:
                return thai_numbers[0]

            def convert_group(n):
                if n == 0:
                    return ""

                result = ""
                length = len(str(n))

                for i in range(length):
                    digit = int(str(n)[i])
                    if digit != 0:
                        if i == 1 and digit == 1:  # กรณีเลข 1 ในหลักสิบให้ใช้ "สิบ" เฉยๆ
                            result += thai_units[length - i - 1]
                        elif i == 1 and digit == 2:  # กรณีเลข 2 ในหลักสิบให้ใช้ "ยี่"
                            result += "ยี่" + thai_units[length - i - 1]
                        elif i == 0 and digit == 1 and length > 1:  # กรณีเลข 1 ในหลักหน่วยและมีหลักอื่นๆ ด้วย
                            result += "เอ็ด"
                        else:
                            result += thai_numbers[digit] + thai_units[length - i - 1]
                return result

            # แยกจำนวนเต็มและทศนิยม
            amount_int = int(number)
            amount_dec = int(round((number - amount_int) * 100))

            result = convert_group(amount_int)
            if amount_dec > 0:
                result += "บาท" + convert_group(amount_dec) + "สตางค์"
            else:
                result += "บาทถ้วน"

            return result

        return thai_number_to_text(self.amount)

    def get_formatted_date(self):
        return self.date.strftime('%B %d, %Y')

    @api.depends('reconciled_bill_ids')
    def _compute_order_lines(self):
        for payment in self:
            payment.order_lines = payment.reconciled_bill_ids.mapped('invoice_line_ids')

    order_lines = fields.One2many('account.move.line', compute='_compute_order_lines')