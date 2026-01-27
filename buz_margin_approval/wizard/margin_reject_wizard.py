# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class MarginRejectWizard(models.TransientModel):
    _name = 'margin.reject.wizard'
    _description = 'Margin Rejection Wizard'
    
    sale_order_id = fields.Many2one('sale.order', string='Sale Order', required=True)
    margin_percentage = fields.Float(related='sale_order_id.margin_percentage', string='Current Margin %', readonly=True)
    rule_id = fields.Many2one(related='sale_order_id.margin_rule_id', string='Applied Rule', readonly=True)
    rejection_reason = fields.Text(string='Rejection Reason', required=True)
    
    def action_reject(self):
        self.ensure_one()
        order = self.sale_order_id
        
        # ตรวจสอบสิทธิ์
        if self.env.user not in order.margin_approval_user_ids and not self.env.user.has_group('buz_margin_approval.group_margin_approval'):
            raise UserError(_("You are not authorized to reject this order's margin."))
        
        # อัพเดทสถานะ
        order.margin_approval_state = 'rejected'
        
        # สร้าง message ที่มีเหตุผลการปฏิเสธ
        body = _(f"Margin Rejected by {self.env.user.name}")
        if self.rejection_reason:
            body += _(f"<br/>Reason: {self.rejection_reason}")
        order.message_post(body=body)
        
        # ส่งอีเมลแจ้งเตือนการปฏิเสธ (ถ้า rule ตั้งค่าให้ส่ง)
        if order.margin_rule_id.send_email:
            self._send_rejection_email()
        
        return {'type': 'ir.actions.act_window_close'}
    
    def _send_rejection_email(self):
        """ส่งอีเมลแจ้งเตือนการปฏิเสธไปยังผู้ขอและผู้เกี่ยวข้อง"""
        self.ensure_one()
        order = self.sale_order_id
        
        # รายชื่อผู้รับอีเมล (ผู้สร้าง SO และพนักงานขาย)
        recipients = []
        if order.create_uid.email:
            recipients.append(order.create_uid.email)
        if order.user_id.email and order.user_id.email != order.create_uid.email:
            recipients.append(order.user_id.email)
            
        if not recipients:
            return
        
        # สร้าง email และส่ง
        email_values = {
            'subject': _('Margin Approval Rejected: %s') % order.name,
            'email_from': order.company_id.email or self.env.user.email_formatted,
            'email_to': ','.join(recipients),
            'body_html': f"""
                <p>เรียนทุกท่านที่เกี่ยวข้อง,</p>
                <p>คำขออนุมัติ margin สำหรับใบเสนอราคาเลขที่ {order.name} ได้ถูกปฏิเสธ</p>
                <ul>
                    <li>ลูกค้า: {order.partner_id.name}</li>
                    <li>ยอดรวม: {order.amount_total} {order.currency_id.symbol}</li>
                    <li>Margin: {order.margin_percentage:.2f}%</li>
                    <li>ปฏิเสธโดย: {self.env.user.name}</li>
                    <li>เหตุผล: {self.rejection_reason or '-'}</li>
                </ul>
                <p>กรุณาปรับปรุงรายการและยื่นขออนุมัติใหม่อีกครั้ง</p>
            """,
            'auto_delete': True,
            'model': 'sale.order',
            'res_id': order.id,
        }
        
        self.env['mail.mail'].sudo().create(email_values).send()
