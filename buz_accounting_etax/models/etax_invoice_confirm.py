from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import requests
import json
import logging

_logger = logging.getLogger(__name__)


class AccountMoveInherit(models.Model):
    _inherit = 'account.move'

    # เพิ่ม field ถ้าต้องการ
    custom_field = fields.Char(string='Custom Field')
    is_custom_confirmed = fields.Boolean(string='Custom Confirmed', default=False)
    sales_order_number = fields.Char(string='Sales Order Number', related='invoice_origin', store=True)

    def action_post(self):
        """
        Override method action_post ที่ถูกเรียกเมื่อกดปุ่ม Confirm
        """
        # ตรวจสอบเงื่อนไขก่อน Confirm
        self._custom_validation_before_confirm()
        
        # เรียก method เดิมของ Odoo
        res = super(AccountMoveInherit, self).action_post()
        
        # ทำงานหลังจาก Confirm สำเร็จ
        self._custom_action_after_confirm()
        
        return res

    def _custom_validation_before_confirm(self):
        """
        ตรวจสอบเงื่อนไขก่อนการ Confirm Invoice
        """
        for move in self:
            # ตัวอย่าง: ตรวจสอบว่ามี Invoice Lines หรือไม่
            if not move.invoice_line_ids:
                raise ValidationError(_('ไม่สามารถ Confirm ได้: ไม่มีรายการสินค้า'))
            
            # ตัวอย่าง: ตรวจสอบ Customer
            if not move.partner_id:
                raise UserError(_('กรุณาระบุลูกค้า'))
            
            # ตัวอย่าง: ตรวจสอบจำนวนเงินขั้นต่ำ
            if move.amount_total < 0:
                raise ValidationError(_('ยอดเงินต้องมากกว่า 0'))
            
            # ตัวอย่าง: ตรวจสอบ Custom Field
            # if not move.custom_field:
            #     raise ValidationError(_('กรุณากรอก Custom Field'))

    def _custom_action_after_confirm(self):
        """
        ทำงานหลังจาก Confirm Invoice สำเร็จ
        """
        for move in self:
            # ตัวอย่าง: Update field
            move.is_custom_confirmed = True
            
            # ตัวอย่าง: สร้าง Log หรือ Activity
            move.message_post(
                body=_('Invoice ถูก Confirm โดย: %s') % self.env.user.name,
                subject=_('Invoice Confirmed')
            )

            # สร้างรายการใน E-tax
            self._create_related_record(move)

    def _create_related_record(self, move):
        """
        สร้างรายการที่เกี่ยวข้องหลัง Confirm
        """

        etax_config = self.env['etax.config'].search([('name', '=', 'UAT')], limit=1)
        sale_order = self.env['sale.order'].search([('name', '=', move.sales_order_number)], limit=1)

        down_payment_lines = move.invoice_line_ids.filtered(lambda l: l.name == 'Down Payment')
    
        # คำนวณผลรวม
        total_amount = sum(down_payment_lines.mapped('price_subtotal'))
        total_with_tax = sum(down_payment_lines.mapped('price_total'))

        # สร้าง record ใน etax.transaction จากข้อมูล invoice หลัก
        etax_transaction = self.env['etax.transaction'].create({
            'invoice_id': move.id,
            'etax_config_id': etax_config.id,
            'partner_id': move.partner_id.id,
            'partner_tax_id': move.partner_id.vat or "",
            'partner_branch_id': "00000",
            'sale_order_ref': sale_order.id if sale_order else None,
            'document_date': move.invoice_date or fields.Date.today(),
            'payment_term': move.invoice_payment_term_id.line_ids[0].nb_days if move.invoice_payment_term_id.line_ids else 0,
            'amount_untaxed': move.amount_untaxed,
            'amount_vat': move.amount_tax,
            'net_amount_total': move.amount_total,
            'amount_total': move.amount_total,
            'deposit': total_amount,
            'notes': move.notes,
        })

        for line in move.invoice_line_ids:
            if line.product_id.name != 'Down Payment':
                self.env['etax.transaction.line'].create({
                    'transaction_id': etax_transaction.id,
                    'product_id': line.product_id.id,
                    'name': line.product_id.name,
                    'quantity': line.quantity,
                    'price_unit': line.price_unit,
                    'discount': line.discount,
                    'price_subtotal': line.price_subtotal,
                    'tax_ids': [(6, 0, line.tax_ids.ids)],
                })

    @api.constrains('invoice_line_ids')
    def _check_invoice_lines(self):
        """
        ตรวจสอบ Invoice Lines แบบ realtime
        """
        for move in self:
            if move.move_type == 'out_invoice':
                for line in move.invoice_line_ids:
                    if line.price_unit <= 0:
                        raise ValidationError(_('ราคาต้องมากกว่า 0'))
