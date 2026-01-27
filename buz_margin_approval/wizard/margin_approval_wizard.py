# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class MarginApprovalWizard(models.TransientModel):
    _name = 'margin.approval.wizard'
    _description = 'Margin Approval Wizard'
    
    sale_order_id = fields.Many2one('sale.order', string='Sale Order', required=True)
    margin_percentage = fields.Float(related='sale_order_id.margin_percentage', string='Current Margin %', readonly=True)
    rule_id = fields.Many2one(related='sale_order_id.margin_rule_id', string='Applied Rule', readonly=True)
    rule_line_id = fields.Many2one(related='sale_order_id.margin_rule_line_id', string='Applied Margin Line', readonly=True)
    note = fields.Text(string='Notes')
    
    def action_send(self):
        """Send approval request"""
        self.ensure_one()
        
        # Send notification to approvers
        self.sale_order_id.approval_state = 'pending'
        self.sale_order_id.approved_user_ids = [(5, 0, 0)]  # Clear previous approvals
        
        msg = _("Margin Approval Requested. Order margin: %.2f%%") % self.sale_order_id.margin_percentage
        if self.note:
            msg += "\n" + _("Note: ") + self.note
        self.sale_order_id.message_post(body=msg)
        
        # Create activities and send email
        self.sale_order_id._create_margin_approval_activities()
        self.sale_order_id._send_margin_approval_email()
        
        return {'type': 'ir.actions.act_window_close'}
