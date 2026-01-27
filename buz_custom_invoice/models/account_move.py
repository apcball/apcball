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
    delivery_price = fields.Monetary(string='Delivery Price')
    delivery_price = fields.Monetary(string="ค่าขนส่ง", currency_field='currency_id')
    return_invoice_id = fields.Many2one('account.move', string='ใบคืนสินค้าอ้างอิง')
    notes = fields.Text(string='หมายเหตุ')
    amount_total_text_th = fields.Char(string="จำนวนเงิน (ตัวอักษร)", compute="_compute_amount_total_text_th", store=True)
    has_vat = fields.Boolean(string='มี VAT', compute='_compute_has_vat')
    original_tax_invoice_amount = fields.Monetary(string='มูลค่าสินค้าตามใบกำกับภาษีเดิม')
    correct_product_value = fields.Monetary(string='มูลค่าของสินค้าที่ถูกต้อง')
    invoice = fields.Char(string="Invoice Ref")  
    picking_id = fields.Many2one('stock.picking', string="ใบรับคืนสินค้า")
    invoice_partner_ref = fields.Char(string="Customer Reference")

    @api.depends('invoice_line_ids.tax_line_id')
    def _compute_has_vat(self):
        for rec in self:
            rec.has_vat = any(tax.name == 'VAT 7%' for line in rec.invoice_line_ids for tax in line.tax_ids)
    
    @api.depends('amount_total')
    def _compute_amount_total_text_th(self):
        for rec in self:
            rec.amount_total_text_th = rec._baht_text_th(rec.amount_total)

    deposit_amount = fields.Monetary(
        string="Deposit",
        compute='_compute_deposit_amount',
        store=True,
        currency_field='currency_id'
    )

    @api.depends('invoice_line_ids')
    def _compute_deposit_amount(self):
        for move in self:
            deposit_total = sum(
                line.price_subtotal for line in move.invoice_line_ids
                if 'มัดจำ' in (line.name or '').lower()
            )
            move.deposit_amount = deposit_total        
            

    def _baht_text_th(self, amount):
        if amount is None:
            return ''

        negative = amount < 0
        amount = abs(float(amount))
        integer_part = int(amount)
        decimal_part = int(round((amount - integer_part) * 100))

        baht_text = self._num2words_th(integer_part)
        if not baht_text:
            baht_text = 'ศูนย์'

        result = ('ลบ' if negative else '') + baht_text + 'บาท'
        if decimal_part > 0:
            result += self._num2words_th(decimal_part) + 'สตางค์'
        else:
            result += 'ถ้วน'
        return result

    def _num2words_th(self, number):
        units = ['', 'หนึ่ง', 'สอง', 'สาม', 'สี่', 'ห้า', 'หก', 'เจ็ด', 'แปด', 'เก้า']
        positions = ['', 'สิบ', 'ร้อย', 'พัน', 'หมื่น', 'แสน']

        def convert_group(number_str):
            words = ''
            length = len(number_str)
            for i in range(length):
                digit = int(number_str[i])
                pos = length - i - 1
                if digit != 0:
                    if pos == 1 and digit == 1:
                        words += 'สิบ'
                    elif pos == 1 and digit == 2:
                        words += 'ยี่สิบ'
                    elif pos == 1:
                        words += units[digit] + 'สิบ'
                    elif pos == 0 and digit == 1 and length > 1:
                        words += 'เอ็ด'
                    else:
                        words += units[digit] + positions[pos]
            return words

        number_str = str(int(number))
        result = ''
        group_count = 0

        while number_str:
            group = number_str[-6:]
            number_str = number_str[:-6]
            group_words = convert_group(group.zfill(6))  # pad 0s if needed
            if group_words:
                if group_count == 0:
                    result = group_words + result
                else:
                    result = group_words + 'ล้าน' * group_count + result
            group_count += 1

        return result

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