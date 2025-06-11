# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class MarginApprovalWizard(models.TransientModel):
    _name = 'margin.approval.wizard'
    _description = 'Margin Approval Wizard'
    
    sale_order_id = fields.Many2one('sale.order', string='Sale Order', required=True)
    margin_percentage = fields.Float(related='sale_order_id.margin_percentage', string='Current Margin %', readonly=True)
    rule_id = fields.Many2one(related='sale_order_id.margin_rule_id', string='Applied Rule', readonly=True)
    note = fields.Text(string='Notes')
    
    def action_send(self):
        self.ensure_one()
        
        # ส่งการแจ้งเตือนให้ผู้อนุมัติ
        self.sale_order_id.margin_approval_state = 'pending'
        
        msg = _("Margin Approval Requested. Order margin: %s%%") % self.sale_order_id.margin_percentage
        if self.note:
            msg += "\nNote: " + self.note
        self.sale_order_id.message_post(body=msg)
        
        # ตรวจสอบการตั้งค่าการส่งอีเมลจาก rule ที่เกี่ยวข้อง
        if self.sale_order_id.margin_rule_id.send_email:
            # Notify the approvers via email subscription
            partner_ids = self.sale_order_id.margin_approval_user_ids.mapped('partner_id').ids
            self.sale_order_id.message_subscribe(partner_ids=partner_ids)
            
            # ส่งการแจ้งเตือนทางอีเมล
            self.sale_order_id._send_margin_approval_email()
        
        return {'type': 'ir.actions.act_window_close'}
