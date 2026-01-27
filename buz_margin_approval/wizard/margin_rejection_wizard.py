# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class MarginRejectionWizard(models.TransientModel):
    _name = 'margin.rejection.wizard'
    _description = 'Margin Rejection Wizard'
    
    sale_order_id = fields.Many2one('sale.order', string='Sale Order', required=True)
    margin_percentage = fields.Float(related='sale_order_id.margin_percentage', string='Current Margin %', readonly=True)
    rule_id = fields.Many2one(related='sale_order_id.margin_rule_id', string='Applied Rule', readonly=True)
    rule_line_id = fields.Many2one(related='sale_order_id.margin_rule_line_id', string='Applied Margin Line', readonly=True)
    rejection_reason = fields.Text(string='Rejection Reason', required=True)
    
    def action_reject(self):
        """Reject the margin approval request with reason"""
        self.ensure_one()
        
        if not self.rejection_reason:
            raise UserError(_("Please provide a rejection reason."))
        
        # Check if user has permission to reject
        sale_order = self.sale_order_id
        if not sale_order._can_approve_margin():
            raise UserError(_("You are not authorized to reject this order's margin."))
            
        # Reject the margin
        sale_order.approval_state = 'rejected'
        sale_order.approved_user_ids = [(5, 0, 0)]  # Clear approvals
        
        # Post rejection message with reason
        body = _("Margin Rejected by %s") % self.env.user.name
        body += "<br/><strong>" + _("Reason:") + "</strong> " + self.rejection_reason
        sale_order.message_post(body=body)
        
        # Mark mail activities as rejected with reason
        sale_order._mark_margin_approval_activities_rejected(self.rejection_reason)
        
        # Create activity to notify salesperson with rejection reason
        sale_order._create_approval_notification_activity('rejected', self.rejection_reason)
        
        return {'type': 'ir.actions.act_window_close'}
