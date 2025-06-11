# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class MarginRejectionWizard(models.TransientModel):
    _name = 'margin.rejection.wizard'
    _description = 'Margin Rejection Wizard'
    
    sale_order_id = fields.Many2one('sale.order', string='Sale Order', required=True)
    margin_percentage = fields.Float(related='sale_order_id.margin_percentage', string='Current Margin %', readonly=True)
    rule_id = fields.Many2one(related='sale_order_id.margin_rule_id', string='Applied Rule', readonly=True)
    rejection_reason = fields.Text(string='Rejection Reason', required=True)
    
    def action_reject(self):
        """Reject the margin approval request with reason"""
        self.ensure_one()
        
        if not self.rejection_reason:
            raise UserError(_("Please provide a rejection reason."))
        
        # Check if user has permission to reject
        sale_order = self.sale_order_id
        if self.env.user not in sale_order.margin_approval_user_ids and \
           not self.env.user.has_group('buz_margin_approval.group_margin_approval'):
            raise UserError(_("You are not authorized to reject this order's margin."))
            
        # Reject the margin
        sale_order.margin_approval_state = 'rejected'
        
        # Post rejection message with reason
        body = _(f"Margin Rejected by {self.env.user.name}")
        body += f"<br/><strong>Reason:</strong> {self.rejection_reason}"
        sale_order.message_post(body=body)
        
        return {'type': 'ir.actions.act_window_close'}
