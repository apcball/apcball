# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools.misc import clean_context


class SaleOrder(models.Model):
    _inherit = 'sale.order'
    
    requires_margin_approval = fields.Boolean(string='Requires Margin Approval', compute='_compute_requires_margin_approval', store=True)
    margin_approval_state = fields.Selection([
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string='Margin Approval Status', copy=False)
    margin_percentage = fields.Float(string='Margin %', compute='_compute_margin_percentage', store=True)
    margin_approval_user_ids = fields.Many2many('res.users', string='Margin Approvers', compute='_compute_margin_approval_users', store=True)
    margin_rule_id = fields.Many2one('margin.approval.rule', string='Applied Margin Rule', compute='_compute_margin_approval_users', store=True)
    is_margin_approved = fields.Boolean(string='Is Margin Approved', compute='_compute_is_margin_approved')
    
    @api.depends('margin', 'amount_untaxed')
    def _compute_margin_percentage(self):
        for order in self:
            if order.amount_untaxed:
                order.margin_percentage = (order.margin / order.amount_untaxed) * 100.0
            else:
                order.margin_percentage = 0.0
    
    @api.depends('margin_percentage')
    def _compute_margin_approval_users(self):
        for order in self:
            rule = self.env['margin.approval.rule'].get_applicable_rule(order.margin_percentage, order.company_id.id)
            order.margin_rule_id = rule.id if rule else False
            order.margin_approval_user_ids = rule.user_ids if rule else False
    
    @api.depends('margin_percentage', 'margin_rule_id')
    def _compute_requires_margin_approval(self):
        for order in self:
            order.requires_margin_approval = bool(order.margin_rule_id)
    
    @api.depends('margin_approval_state', 'requires_margin_approval')
    def _compute_is_margin_approved(self):
        for order in self:
            order.is_margin_approved = (not order.requires_margin_approval) or (order.margin_approval_state == 'approved')
    
    def _can_approve_margin(self):
        """Check if current user can approve this order's margin"""
        self.ensure_one()
        if self.env.user.has_group('buz_margin_approval.group_margin_approval'):
            return True
        return self.env.user in self.margin_approval_user_ids
    
    def action_confirm(self):
        for order in self:
            if order.requires_margin_approval and not order.is_margin_approved:
                raise UserError(_(
                    f"Cannot confirm! This order has a margin of {order.margin_percentage:.2f}% which requires approval. "
                    f"Please use 'Request Margin Approval' button and wait for approval from an authorized person."
                ))
        return super(SaleOrder, self).action_confirm()
    
    def action_request_margin_approval(self):
        self.ensure_one()
        if not self.requires_margin_approval:
            raise UserError(_("This order does not require margin approval."))
        
        if not self.margin_approval_user_ids:
            raise UserError(_("No approvers defined for this margin range."))
        
        self.margin_approval_state = 'pending'
        
        # Create a record in mail thread for traceability
        body = _(f"Margin Approval Requested. Order margin: {self.margin_percentage:.2f}%")
        self.message_post(body=body)
        
        # ตรวจสอบการตั้งค่าการส่งอีเมลจาก rule ที่เกี่ยวข้อง
        if self.margin_rule_id.send_email:
            # Notify the approvers via email
            partner_ids = self.margin_approval_user_ids.mapped('partner_id').ids
            self.message_subscribe(partner_ids=partner_ids)
            
            # ส่งการแจ้งเตือนทางอีเมล
            self._send_margin_approval_email()
        
        return {
            'name': _('Margin Approval'),
            'view_mode': 'form',
            'res_model': 'margin.approval.wizard',
            'type': 'ir.actions.act_window',
            'target': 'new',
            'context': {'default_sale_order_id': self.id}
        }
    
    def action_approve_margin(self):
        self.ensure_one()
        if self.env.user not in self.margin_approval_user_ids and not self.env.user.has_group('buz_margin_approval.group_margin_approval'):
            raise UserError(_("You are not authorized to approve this order's margin."))
        
        self.margin_approval_state = 'approved'
        body = _(f"Margin Approved by {self.env.user.name}")
        self.message_post(body=body)
        
        # เดิม: เมื่ออนุมัติแล้ว ให้ confirm ทันที (return self.action_confirm())
        # ใหม่: แค่อนุมัติ ไม่ confirm อัตโนมัติ ให้ user กดปุ่ม Confirm เอง
        return True
    
    def action_view_order(self):
        """Open the sale order form view when clicking on the 'View Order' button in kanban view"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current'
        }
    
    def action_reject_margin(self):
        self.ensure_one()
        if self.env.user not in self.margin_approval_user_ids and not self.env.user.has_group('buz_margin_approval.group_margin_approval'):
            raise UserError(_("You are not authorized to reject this order's margin."))
        
        # Open the rejection wizard instead of directly rejecting
        return {
            'name': _('Reject Margin'),
            'view_mode': 'form',
            'res_model': 'margin.rejection.wizard',
            'type': 'ir.actions.act_window',
            'target': 'new',
            'context': {'default_sale_order_id': self.id}
        }
        
    def _send_margin_approval_email(self):
        """ส่งอีเมลแจ้งเตือนไปยังผู้อนุมัติ"""
        self.ensure_one()
        
        # ส่งอีเมลให้แต่ละผู้อนุมัติ
        for user in self.margin_approval_user_ids:
            if not user.email:
                continue
                
            # สร้าง email template ด้วย code แทนการใช้ xml template
            mail_values = {
                'subject': _('Margin Approval Request: %s') % self.name,
                'email_from': self.company_id.email or self.env.user.email_formatted,
                'email_to': user.email,
                'body_html': f"""
                    <p>เรียน {user.name},</p>
                    <p>มีคำขออนุมัติ margin สำหรับใบเสนอราคาเลขที่ {self.name}</p>
                    <ul>
                        <li>ลูกค้า: {self.partner_id.name}</li>
                        <li>ยอดรวม: {self.amount_total} {self.currency_id.symbol}</li>
                        <li>Margin: {self.margin_percentage:.2f}%</li>
                        <li>พนักงานขาย: {self.user_id.name}</li>
                    </ul>
                    <p>กรุณาเข้าสู่ระบบเพื่อทำการอนุมัติหรือปฏิเสธคำขอนี้</p>
                    <p>ขอบคุณครับ/ค่ะ</p>
                """,
                'auto_delete': True,
                'model': 'sale.order',
                'res_id': self.id,
            }
            
            # ส่งอีเมล
            self.env['mail.mail'].sudo().create(mail_values).send()
    
    @api.model
    def action_get_approval_orders(self):
        """Return action to display orders waiting for the user's approval"""
        return {
            'name': _('Orders Pending Your Approval'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'tree,form',
            'domain': [
                ('margin_approval_state', '=', 'pending'),
                '|',
                ('margin_approval_user_ids', 'in', self.env.user.id),
                '|',
                ('create_uid', '=', self.env.user.id),
                ('user_id', '=', self.env.user.id)
            ],
            'context': {'search_default_pending_margin_approval': 1},
        }
    
    def write(self, vals):
        # ตรวจสอบการแก้ไข order line ที่เกี่ยวกับราคา/ส่วนลด
        reset_approval = False
        if 'order_line' in vals:
            for command in vals['order_line']:
                # command[0] == 0: create, 1: update, 2: delete
                if command[0] in (0, 1):
                    line_vals = command[2] if len(command) > 2 else {}
                    if any(field in line_vals for field in ['price_unit', 'discount']):
                        reset_approval = True
                elif command[0] == 2:
                    reset_approval = True
        # ตรวจสอบการแก้ไข field อื่นๆ ที่เกี่ยวกับราคา/ส่วนลดใน order
        if any(f in vals for f in ['amount_untaxed', 'margin']):
            reset_approval = True
        # ถ้าเคย approved แล้ว และมีการแก้ไข ให้กลับไป pending
        if reset_approval and self.margin_approval_state == 'approved':
            vals['margin_approval_state'] = 'pending'
        return super(SaleOrder, self).write(vals)
