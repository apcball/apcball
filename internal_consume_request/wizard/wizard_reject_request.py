# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class InternalConsumeRequestReject(models.TransientModel):
    _name = 'internal.consume.request.reject'
    _description = 'Reject Internal Consume Request'

    request_id = fields.Many2one(
        'internal.consume.request',
        string='Request',
        required=True
    )
    
    reason = fields.Text(
        string='Rejection Reason',
        required=True
    )

    def action_reject_request(self):
        """Reject the request with reason"""
        self.ensure_one()
        if not self.reason:
            raise UserError(_('Please provide a rejection reason.'))
        
        self.request_id._action_reject_with_reason(self.reason)
        
        return {'type': 'ir.actions.act_window_close'}
