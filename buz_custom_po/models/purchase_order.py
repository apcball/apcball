# -*- coding: utf-8 -*-
from odoo import models, fields, api

class PurchaseOrderInherit(models.Model):
    _inherit = 'purchase.order'
    _description = 'Purchase Order Inherit'

    amount_untaxed_before_discount = fields.Monetary(
        string='Amount Before Discount',
        compute='_compute_amount',
        store=True,
        tracking=True,
    )
    amount_discount = fields.Monetary(
        string='Discount Amount',
        compute='_compute_amount',
        store=True,
        tracking=True,
    )
    amount_after_discount = fields.Monetary(
        string='Amount After Discount',
        compute='_compute_amount',
        store=True,
        tracking=True,
    )

    @api.depends('order_line.price_total', 'order_line.price_unit', 'order_line.product_qty', 'order_line.discount')
    def _compute_amount(self):
        for order in self:
            amount_untaxed_before_discount = 0.0
            amount_discount = 0.0

            for line in order.order_line:
                # คำนวณราคาก่อนหักส่วนลด (QTY * Unit Price)
                line_total = line.product_qty * line.price_unit
                amount_untaxed_before_discount += line_total

                # คำนวณส่วนลดสำหรับแต่ละรายการ
                if hasattr(line, 'discount') and line.discount:
                    discount_amount = line_total * (line.discount / 100.0)
                    amount_discount += discount_amount

            # คำนวณราคาหลังหักส่วนลด
            amount_after_discount = amount_untaxed_before_discount - amount_discount
            # คำนวณภาษี 7% จากราคาหลังหักส่วนลด
            amount_tax = amount_after_discount * 0.07

            order.update({
                'amount_untaxed_before_discount': amount_untaxed_before_discount,  # ราคารวม/Total
                'amount_discount': amount_discount,  # ส่วนลด/Discount
                'amount_after_discount': amount_after_discount,  # ราคาหลังหักส่วนลด/Net
                'amount_tax': amount_tax,  # ภาษีมูลค่าเพิ่ม/VAT 7%
                'amount_total': amount_after_discount + amount_tax,  # รวมทั้งสิ้น/Grand Total
            })