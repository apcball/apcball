from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import timedelta
from odoo.tools import html2plaintext
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
    # เพิ่มฟิลด์เพื่อเก็บค่า advance_payment_method จาก wizard
    advance_payment_method = fields.Selection([
        ('delivered', 'Regular invoice'),
        ('percentage', 'Down payment (percentage)'),
        ('fixed', 'Down payment (fixed amount)'),
    ], string='Invoice Payment Method', copy=False, help='Payment method used when creating this invoice from sale order')

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
            
            # ตรวจสอบ Partner เฉพาะสำหรับ Invoice เท่านั้น (ไม่บังคับสำหรับ Journal Entry)
            if move.move_type in ['out_invoice', 'in_invoice', 'out_refund', 'in_refund']:
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
        ทำงานเฉพาะ invoice/credit note เท่านั้น
        ไม่ทำงานสำหรับ Journal Entry ทั่วไป (เช่น clearing entry)
        """
        for move in self:
            # Update field
            move.is_custom_confirmed = True

            # สร้าง Log หรือ Activity
            move.message_post(
                body=_('Invoice ถูก Confirm โดย: %s') % self.env.user.name,
                subject=_('Invoice Confirmed')
            )

            # สร้างรายการใน E-tax เฉพาะ Invoice / Credit Note เท่านั้น
            # -- ข้าม General Journal Entry (move_type='entry') เช่น clearing, adjustment, etc.
            if move.move_type not in ('out_invoice', 'in_invoice', 'out_refund', 'in_refund'):
                continue

            # ข้ามกรณีไม่มี partner (ป้องกัน not-null constraint)
            if not move.partner_id:
                _logger.warning(
                    'buz_accounting_etax: skipping etax creation for move %s '
                    '(no partner_id set).', move.name)
                continue

            # สร้างรายการใน E-tax
            self._create_related_record(move)

    def _create_related_record(self, move):
        """
        สร้างรายการที่เกี่ยวข้องหลัง Confirm
        """

        etax_config = self.env['etax.config'].search([('active', '=', True)], limit=1)
        sale_order = self.env['sale.order'].search([('name', '=', move.sales_order_number)], limit=1)

        # ตรวจสอบประเภท invoice จาก sale order หรือจากรายการสินค้า
        invoice_type = move.advance_payment_method or 'delivered'

        down_payment_lines = move.invoice_line_ids.filtered(lambda l: l.is_downpayment)
    
        # คำนวณผลรวม
        total_amount = sum(down_payment_lines.mapped('price_subtotal'))
        total_with_tax = sum(down_payment_lines.mapped('price_total'))

        # คำนวณผลรวม Down payment สำหรับ invoice_type = delivered (ยอดเงินมัดจำ)
        if invoice_type == 'delivered':
            down_payment_product_lines = move.invoice_line_ids.filtered(lambda l: l.product_id.service_policy == 'ordered_prepaid')
            total_amount = abs(sum(down_payment_product_lines.mapped('price_subtotal')))

        if move.move_type == 'out_invoice': # Customers / Invoices
            document_type = 'T03'
        elif move.move_type == 'out_refund': # Customer / Credit Notes
            document_type = '81'
        else:
            document_type = 'T03' # ค่าเริ่มต้น

        # สร้าง record ใน etax.transaction จากข้อมูล invoice หลัก
        # คำนวณวันที่ครบกำหนดชำระ (ดึงจากรายการที่มีจำนวนวันมากที่สุด)
        if move.invoice_payment_term_id.line_ids:
            # ดึงรายการที่มี nb_days มากที่สุด
            payment_term_days = max(move.invoice_payment_term_id.line_ids.mapped('nb_days'))
        else:
            payment_term_days = 0

        calculated_due_date = move.invoice_date + timedelta(days=payment_term_days) if move.invoice_date else fields.Date.today()
        
        # ดึงข้อมูลและลบ HTML tags
        terms = move.narration
        narration = html2plaintext(terms) if terms else ""

        # ค้นหา invoice จากชื่อที่อยู่ใน move.ref
        selected_invoice_id = False
        if move.ref:
            # พยายามดึงชื่อ invoice จาก ref (เช่น "Reversal of: MIV-25120074, test")
            invoice_name = None
            if ': ' in move.ref:
                # แยกชื่อ invoice ออกมา
                parts = move.ref.split(': ')
                if len(parts) > 1:
                    invoice_name = parts[1].split(',')[0].strip()
            
            # ค้นหา invoice จากชื่อ
            if invoice_name:
                related_invoice = self.env['account.move'].sudo().search([
                    ('name', '=', invoice_name),
                    ('move_type', 'in', ['out_invoice', 'out_refund']),
                    ('state', '=', 'posted')
                ], limit=1)
                if related_invoice:
                    selected_invoice_id = related_invoice.id

        # สร้าง record ใน etax.transaction จากข้อมูล invoice หลัก
        etax_transaction = self.env['etax.transaction'].create({
            'invoice_id': move.id,
            'document_type': document_type,
            'etax_config_id': etax_config.id,
            'partner_id': move.partner_id.id,
            'partner_tax_id': move.partner_id.vat or "",
            'partner_branch_id': "00000",
            'sale_order_ref': sale_order.id if sale_order else None,
            'selected_invoice_id': selected_invoice_id,
            'document_date': move.invoice_date or fields.Date.today(),
            'payment_term': payment_term_days,
            'payment_due_date': calculated_due_date,
            # 'payment_term': move.invoice_payment_term_id.line_ids[0].nb_days if move.invoice_payment_term_id.line_ids else 0,
            'amount_untaxed': move.amount_untaxed,
            'amount_vat': move.amount_tax,
            'net_amount_total': move.amount_total,
            'amount_total': move.amount_total,
            'deposit': total_amount
            # 'notes': narration or "",
            # 'notes': invoice_type,
        })

        for line in move.invoice_line_ids:
            if line.price_subtotal != 0 and line.product_id.name:
                self.env['etax.transaction.line'].create({
                        'transaction_id': etax_transaction.id,
                        'product_id': line.product_id.id if line.product_id else False,
                        'name': line.name or (line.product_id.name if line.product_id else ''),
                        'quantity': line.quantity,
                        'price_unit': line.price_unit,
                        'discount': line.discount,
                        'price_subtotal': line.price_subtotal,
                        'tax_ids': [(6, 0, line.tax_ids.ids)]
                    })

                # # ข้ามรายการ down payment ที่มี service_policy = 'ordered_prepaid'
                # # if line.product_id and hasattr(line.product_id, 'service_policy') and line.product_id.service_policy == 'ordered_prepaid':
                # #     continue

                # service_policy = line.product_id.service_policy if line.product_id and hasattr(line.product_id, 'service_policy') else ''
                # invoice_policy = line.product_id.invoice_policy if line.product_id and hasattr(line.product_id, 'invoice_policy') else ''
                
                # # สร้างรายการสำหรับสินค้าปกติ
                # if invoice_type == 'delivered' and line.price_subtotal >= 0:
                #     self.env['etax.transaction.line'].create({
                #         'transaction_id': etax_transaction.id,
                #         'product_id': line.product_id.id if line.product_id else False,
                #         'name': line.name or (line.product_id.name if line.product_id else ''),
                #         'quantity': line.quantity,
                #         'price_unit': line.price_unit,
                #         'discount': line.discount,
                #         'price_subtotal': line.price_subtotal,
                #         'tax_ids': [(6, 0, line.tax_ids.ids)],
                #         'service_policy': service_policy,
                #         'invoice_policy': invoice_policy,
                #     })
                # # สร้างรายการสำหรับ down payment invoice
                # elif invoice_type in ['percentage', 'fixed']:
                #     self.env['etax.transaction.line'].create({
                #         'transaction_id': etax_transaction.id,
                #         'product_id': line.product_id.id if line.product_id else False,
                #         'name': line.name or (line.product_id.name if line.product_id else ''),
                #         'quantity': line.quantity,
                #         'price_unit': line.price_unit,
                #         'discount': line.discount,
                #         'price_subtotal': line.price_subtotal,
                #         'tax_ids': [(6, 0, line.tax_ids.ids)],
                #         'service_policy': service_policy,
                #         'invoice_policy': invoice_policy,
                #     })

    @api.constrains('invoice_line_ids')
    def _check_invoice_lines(self):
        """
        ตรวจสอบ Invoice Lines แบบ realtime
        """
        # for move in self:
        #     if move.move_type == 'out_invoice':
        #         for line in move.invoice_line_ids:
        #             if line.price_unit <= 0:
        #                 raise ValidationError(_('ราคาต้องมากกว่า 0'))
