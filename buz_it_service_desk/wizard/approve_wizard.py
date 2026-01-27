# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ApproveWizard(models.TransientModel):
    _name = 'approve.wizard'
    _description = 'Approval Wizard'
    
    request_id = fields.Integer(string='Request ID')
    request_type = fields.Selection([
        ('service', 'Service Request'),
        ('purchase', 'Purchase Request'),
    ], string='Request Type', required=True)
    
    approve = fields.Boolean(string='Approve', default=True)
    notes = fields.Text(string='Notes')
    
    @api.model
    def default_get(self, fields):
        res = super(ApproveWizard, self).default_get(fields)
        context = self.env.context
        
        if 'active_ids' in context:
            res['request_id'] = context['active_ids'][0] if context['active_ids'] else False
        
        if 'default_request_type' in context:
            res['request_type'] = context['default_request_type']
            
        return res
    
    def action_approve(self):
        """Process the approval or rejection"""
        self.ensure_one()
        
        if self.request_type == 'service':
            request = self.env['it.service.request'].browse(self.request_id)
            if not request.exists():
                raise UserError(_('Service Request not found'))
                
            if self.approve:
                if request.state == 'manager_approve':
                    request.action_manager_approve()
                elif request.state == 'it_approve':
                    request.action_it_approve()
                else:
                    raise UserError(_('Cannot approve request in current state'))
                
                # Add notes if provided
                if self.notes:
                    request.message_post(body=_("Approval Notes: %s") % self.notes)
            else:
                if request.state == 'manager_approve':
                    request.action_manager_reject()
                elif request.state == 'it_approve':
                    request.action_it_reject()
                else:
                    raise UserError(_('Cannot reject request in current state'))
                
                # Add notes if provided
                if self.notes:
                    request.message_post(body=_("Rejection Notes: %s") % self.notes)
                    
        elif self.request_type == 'purchase':
            request = self.env['it.purchase.request'].browse(self.request_id)
            if not request.exists():
                raise UserError(_('Purchase Request not found'))
                
            if self.approve:
                if request.purchase_state == 'manager_approve':
                    request.action_manager_approve()
                elif request.purchase_state == 'it_approve':
                    request.action_it_approve()
                elif request.purchase_state == 'finance_approve':
                    request.action_finance_approve()
                else:
                    raise UserError(_('Cannot approve request in current state'))
                
                # Add notes if provided
                if self.notes:
                    request.message_post(body=_("Approval Notes: %s") % self.notes)
            else:
                if request.purchase_state == 'manager_approve':
                    request.action_manager_reject()
                elif request.purchase_state == 'it_approve':
                    request.action_it_reject()
                elif request.purchase_state == 'finance_approve':
                    request.action_finance_reject()
                else:
                    raise UserError(_('Cannot reject request in current state'))
                
                # Add notes if provided
                if self.notes:
                    request.message_post(body=_("Rejection Notes: %s") % self.notes)
        
        return {'type': 'ir.actions.act_window_close'}