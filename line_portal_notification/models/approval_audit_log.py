# -*- coding: utf-8 -*-
"""
Approval Audit Log Model
========================

This model stores immutable audit logs for all approval actions.
Records cannot be modified or deleted after creation.
"""

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ApprovalAuditLog(models.Model):
    _name = 'approval.audit.log'
    _description = 'Approval Audit Log'
    _order = 'create_date desc'
    _rec_name = 'display_name'

    # Document reference
    res_model = fields.Char(
        string='Document Model',
        required=True,
        readonly=True,
        index=True,
    )
    res_id = fields.Integer(
        string='Document ID',
        required=True,
        readonly=True,
        index=True,
    )
    res_name = fields.Char(
        string='Document Name',
        readonly=True,
    )
    
    # Action details
    action = fields.Selection([
        ('notification_sent', 'Notification Sent'),
        ('portal_viewed', 'Portal Viewed'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('token_expired', 'Token Expired'),
        ('rate_limited', 'Rate Limited'),
        ('invalid_access', 'Invalid Access Attempt'),
    ], string='Action', required=True, readonly=True, index=True)
    
    # Approver information
    approver_id = fields.Many2one(
        'res.users',
        string='Approver',
        readonly=True,
        ondelete='set null',
    )
    line_user_id = fields.Char(
        string='LINE User ID',
        readonly=True,
    )
    
    # Token information
    token_id = fields.Many2one(
        'approval.token',
        string='Token',
        readonly=True,
        ondelete='set null',
    )
    token_value = fields.Char(
        string='Token Value (masked)',
        readonly=True,
    )
    
    # Request information
    ip_address = fields.Char(
        string='IP Address',
        readonly=True,
    )
    user_agent = fields.Char(
        string='User Agent',
        readonly=True,
    )
    
    # Timestamps
    action_datetime = fields.Datetime(
        string='Action Datetime',
        default=fields.Datetime.now,
        required=True,
        readonly=True,
    )
    
    # Additional details
    notes = fields.Text(
        string='Notes',
        readonly=True,
    )
    
    # Computed display name
    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name',
        store=True,
    )
    
    @api.depends('res_name', 'action', 'action_datetime')
    def _compute_display_name(self):
        """Compute display name for the audit log."""
        action_labels = dict(self._fields['action'].selection)
        for log in self:
            action_label = action_labels.get(log.action, log.action)
            doc_name = log.res_name or f"{log.res_model}/{log.res_id}"
            log.display_name = f"{doc_name} - {action_label}"

    @api.model_create_multi
    def create(self, vals_list):
        """
        Create audit log entries.
        Mask token values for security.
        """
        for vals in vals_list:
            # Mask token value if provided
            if vals.get('token_value'):
                token = vals['token_value']
                if len(token) > 8:
                    vals['token_value'] = f"{token[:4]}...{token[-4:]}"
                    
        return super().create(vals_list)

    def write(self, vals):
        """Prevent modification of audit logs."""
        raise UserError(_("Audit logs cannot be modified. They are immutable for security purposes."))

    def unlink(self):
        """Prevent deletion of audit logs."""
        raise UserError(_("Audit logs cannot be deleted. They are immutable for security purposes."))

    @api.model
    def log_action(self, res_model, res_id, action, approver_id=None, 
                   line_user_id=None, token_id=None, token_value=None,
                   ip_address=None, user_agent=None, res_name=None, notes=None):
        """
        Create an audit log entry.
        
        Args:
            res_model: Document model name
            res_id: Document ID
            action: Action type (from selection)
            approver_id: Approver user ID (optional)
            line_user_id: LINE user ID (optional)
            token_id: Token record ID (optional)
            token_value: Token string value (optional, will be masked)
            ip_address: Client IP address (optional)
            user_agent: Client user agent (optional)
            res_name: Document display name (optional)
            notes: Additional notes (optional)
            
        Returns:
            approval.audit.log record
        """
        return self.sudo().create({
            'res_model': res_model,
            'res_id': res_id,
            'action': action,
            'approver_id': approver_id,
            'line_user_id': line_user_id,
            'token_id': token_id,
            'token_value': token_value,
            'ip_address': ip_address,
            'user_agent': user_agent,
            'res_name': res_name,
            'notes': notes,
            'action_datetime': fields.Datetime.now(),
        })
