import json
from odoo import models, fields, api
from math import floor

class AccountMove(models.Model):
    _inherit = 'account.move'

    # ฟิลด์ที่เกี่ยวข้อง
    custom_reference = fields.Char(string="Custom Reference")
    delivery_note = fields.Text(string='Delivery Note')
    total_amount = fields.Float(string='จำนวนเงิน/Total Amount', compute='_compute_total_amount', store=True, digits=(16, 2))
    deposit = fields.Float(string='หักเงินมัดจำ/Deposit', compute='_compute_deposit', store=True, digits=(16, 2))
    sub_total = fields.Float(string='จำนวนเงินหลังหักเงินมัดจำ/Sub Total', compute='_compute_sub_total', store=True, digits=(16, 2))
    amount_after_discount = fields.Float(string='จำนวนเงินหลังหักส่วนลด', compute='_compute_amount_after_discount', store=True, digits=(16, 2))
    vat_7_percent = fields.Float(string='ภาษีมูลค่าเพิ่ม/Vat 7%', compute='_compute_vat_7_percent', store=True, digits=(16, 2))
    grand_total = fields.Float(string='จำนวนเงินรวมทั้งสิ้น/Grand Total', compute='_compute_grand_total', store=True, digits=(16, 2))
    stored_grand_total = fields.Float(string='Stored Grand Total', store=True, digits=(16, 2))
    amount_total_words = fields.Text(string='จำนวนเงินรวมทั้งสิ้นในคำอ่าน', compute='_compute_amount_total_words', store=True)
    purchase_order_number = fields.Char(string='เลขที่ใบสั่งซื้อ', related='purchase_id.name', store=True)
    picking_ids = fields.Many2many('stock.picking', string='Delivery Orders', compute='_compute_picking_ids', store=True)
    delivery_document_number = fields.Char(string="Delivery Document Number")

    @api.depends('invoice_origin', 'purchase_id')
    def _compute_picking_ids(self):
        """Compute the related delivery orders (stock.picking) for this invoice"""
        for move in self:
            pickings = self.env['stock.picking']
            # If we have a purchase order, get its pickings
            if move.purchase_id:
                pickings |= move.purchase_id.picking_ids
            # If we have an invoice origin, try to find related pickings
            elif move.invoice_origin:
                # Try to find sale order
                sale_orders = self.env['sale.order'].search([('name', '=', move.invoice_origin)])
                for order in sale_orders:
                    pickings |= order.picking_ids
                # Try to find purchase order if no sale order
                if not sale_orders:
                    purchase_orders = self.env['purchase.order'].search([('name', '=', move.invoice_origin)])
                    for order in purchase_orders:
                        pickings |= order.picking_ids
                # Try to find pickings directly
                if not pickings:
                    pickings |= self.env['stock.picking'].search([('name', '=', move.invoice_origin)])
                    pickings |= self.env['stock.picking'].search([('origin', '=', move.invoice_origin)])
            move.picking_ids = pickings

    @api.depends('invoice_line_ids.price_unit', 'invoice_line_ids.quantity')
    def _compute_total_amount(self):
        """
        คำนวณยอดรวม (Total Amount) จากรายการสินค้าในใบแจ้งหนี้
        """
        for record in self:
            total_amount = sum(line.price_unit * line.quantity for line in record.invoice_line_ids)
            record.total_amount = round(max(total_amount, 0), 2)

    @api.depends('invoice_payments_widget')
    def _compute_deposit(self):
        """
        คำนวณยอด Deposit จากข้อมูลการชำระเงินใน invoice_payments_widget
        """
        for record in self:
            deposit_total = 0.0
            if record.invoice_payments_widget:
                try:
                    # แปลง JSON ใน invoice_payments_widget เป็น Python dictionary
                    payments_data = json.loads(record.invoice_payments_widget)
                    if 'content' in payments_data:
                        # รวมยอดเงินจากข้อมูลการชำระเงิน
                        deposit_total = sum(payment['amount'] for payment in payments_data['content'])
                except Exception as e:
                    # หากเกิดข้อผิดพลาด ให้ตั้งค่า deposit เป็น 0
                    deposit_total = 0.0
            record.deposit = round(deposit_total, 2)

    @api.depends('total_amount', 'deposit')
    def _compute_sub_total(self):
        """
        คำนวณ Sub Total โดยหักยอด Deposit ออกจาก Total Amount
        """
        for record in self:
            sub_total = record.total_amount - record.deposit
            record.sub_total = round(max(sub_total, 0), 2)

    @api.depends('invoice_line_ids.price_unit', 'invoice_line_ids.quantity', 'invoice_line_ids.discount')
    def _compute_amount_after_discount(self):
        """
        คำนวณยอดรวมหลังหักส่วนลด (Amount After Discount)
        """
        for record in self:
            amount_after_discount = 0.0
            for line in record.invoice_line_ids:
                discount = line.discount or 0.0  # ตรวจสอบว่า discount มีค่าเป็น None หรือไม่
                price = line.price_unit * (1 - (discount / 100.0))
                amount_after_discount += price * line.quantity
            record.amount_after_discount = round(max(amount_after_discount, 0), 2)

    @api.depends('amount_after_discount')
    def _compute_vat_7_percent(self):
        """
        คำนวณภาษีมูลค่าเพิ่ม 7% (VAT 7%)
        """
        for record in self:
            vat = record.amount_after_discount * 0.07
            record.vat_7_percent = round(vat, 2)

    @api.depends('amount_after_discount', 'vat_7_percent')
    def _compute_grand_total(self):
        """
        คำนวณยอดรวมทั้งสิ้น (Grand Total) รวมภาษีมูลค่าเพิ่ม
        """
        for record in self:
            grand_total = record.amount_after_discount + record.vat_7_percent
            record.grand_total = round(grand_total, 2)
            record.stored_grand_total = record.grand_total

    def baht_text(self, amount):
        """
        แปลงจำนวนเงินเป็นข้อความภาษาไทย
        """
        if amount < 0:
            return "จำนวนเงินต้องไม่ติดลบ"

        try:
            amount = round(amount, 2)
            amount_int = int(floor(amount))
            amount_dec = int(round((amount - amount_int) * 100))

            t1 = ["ศูนย์", "หนึ่ง", "สอง", "สาม", "สี่", "ห้า", "หก", "เจ็ด", "แปด", "เก้า"]
            t2 = ["", "สิบ", "ร้อย", "พัน", "หมื่น", "แสน", "ล้าน"]

            def number_to_text(number):
                if number == 0:
                    return "ศูนย์"

                text = ""
                num_str = str(number)
                num_len = len(num_str)

                for i in range(num_len):
                    n = int(num_str[i])
                    if n != 0:
                        if i == (num_len - 1) and n == 1 and num_len > 1:
                            text += "เอ็ด"
                        elif i == (num_len - 2) and n == 2:
                            text += "ยี่"
                        elif i == (num_len - 2) and n == 1:
                            text += ""
                        else:
                            text += t1[n]

                        if n != 0:
                            text += t2[num_len - i - 1]

                return text

            result = number_to_text(amount_int) + "บาท"
            if amount_dec > 0:
                result += number_to_text(amount_dec) + "สตางค์"
            else:
                result += "ถ้วน"

            return result
        except Exception as e:
            return f"ไม่สามารถแปลงจำนวนเงินเป็นคำอ่านได้: {str(e)}"

    @api.depends('stored_grand_total')
    def _compute_amount_total_words(self):
        """
        แปลงยอดรวมทั้งสิ้นเป็นข้อความภาษาไทย
        """
        for record in self:
            try:
                amount = float(record.stored_grand_total or 0.0)
                record.amount_total_words = self.baht_text(amount)
            except Exception:
                record.amount_total_words = "ไม่สามารถแปลงจำนวนเงินเป็นคำอ่านได้"