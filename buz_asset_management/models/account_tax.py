# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AccountTax(models.Model):
    _inherit = 'account.tax'

    buz_vat_non_recoverable = fields.Boolean(
        string='ภาษีซื้อขอคืนไม่ได้ (รวมเป็นต้นทุนทรัพย์สิน)', copy=False,
        help="ภาษีนี้ไม่ใช่ภาษีซื้อที่ขอคืนได้ ยอดภาษีของรายการที่ใช้ภาษีนี้จะรวมเป็นราคาทุนเมื่อสร้างทรัพย์สินจากใบแจ้งหนี้ "
             "ต้องเป็นภาษีที่ลงบัญชีนอกบัญชีภาษี (ไม่ใช้ในการปิดภาษี) เพื่อให้ตรงกับ GL")

    @api.constrains('buz_vat_non_recoverable', 'type_tax_use', 'amount_type', 'invoice_repartition_line_ids')
    def _check_buz_vat_non_recoverable(self):
        for tax in self.filtered('buz_vat_non_recoverable'):
            if tax.type_tax_use != 'purchase' or tax.amount_type != 'percent' or tax.amount <= 0:
                raise ValidationError(_(
                    "ภาษี '%s': ระบุเป็นภาษีซื้อขอคืนไม่ได้ได้เฉพาะภาษีซื้อแบบเปอร์เซ็นต์ที่มากกว่าศูนย์", tax.name))
            tax_lines = tax.invoice_repartition_line_ids.filtered(lambda r: r.repartition_type == 'tax')
            if not tax_lines or any(r.use_in_tax_closing or not r.account_id for r in tax_lines):
                raise ValidationError(_(
                    "ภาษี '%s': ภาษีซื้อขอคืนไม่ได้ต้องกำหนดบัญชีในการแบ่งสัดส่วนภาษี และต้องไม่ใช้ในการปิดภาษี "
                    "มิฉะนั้นยอดใน GL จะไม่ตรงกับทะเบียนทรัพย์สิน", tax.name))
