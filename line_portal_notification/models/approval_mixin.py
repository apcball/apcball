# -*- coding: utf-8 -*-
"""
Approval Mixin
==============

This mixin provides LINE approval notification functionality to any model.
Inherit from 'line.approval.mixin' to add LINE approval capabilities.

Usage:
------
class YourModel(models.Model):
    _name = 'your.model'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'line.approval.mixin']
    
    # Add approver field
    approver_id = fields.Many2one('res.users', string='Approver')
    
    # Override these methods for custom behavior:
    # - _get_line_approval_approver()
    # - _get_line_approval_document_name()
    # - _get_line_approval_amount()
    # - _get_line_approval_message()
    # - action_approve()
    # - action_reject()
"""

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class LineApprovalMixin(models.AbstractModel):
    _name = 'line.approval.mixin'
    _description = 'LINE Approval Mixin'

    # Track if LINE notification was sent
    line_notification_sent = fields.Boolean(
        string='LINE Notification Sent',
        default=False,
        copy=False,
        readonly=True,
    )
    line_notification_datetime = fields.Datetime(
        string='LINE Notification Sent On',
        copy=False,
        readonly=True,
    )
    
    # Related approval token
    approval_token_id = fields.Many2one(
        'approval.token',
        string='Approval Token',
        copy=False,
        readonly=True,
    )

    def _get_line_approval_approver(self):
        """
        Get the approver user for LINE notification.
        Override this method to customize approver selection.
        
        Returns:
            res.users record
        """
        self.ensure_one()
        # Try common field names
        for field_name in ['approver_id', 'approval_user_id', 'reviewer_id', 'manager_id']:
            if hasattr(self, field_name):
                approver = getattr(self, field_name)
                if approver:
                    return approver
        return False

    def _get_line_approval_document_name(self):
        """
        Get the document reference/name for the LINE message.
        Override this method to customize the document name.
        
        Returns:
            str: Document reference
        """
        self.ensure_one()
        # Try common field names
        for field_name in ['name', 'display_name', 'reference', 'ref']:
            if hasattr(self, field_name):
                value = getattr(self, field_name)
                if value:
                    return value
        return f"{self._name}/{self.id}"

    def _get_line_approval_amount(self):
        """
        Get the amount to display in LINE message.
        Override this method to customize amount display.
        
        Returns:
            str: Formatted amount string or None
        """
        self.ensure_one()
        # Try common field names
        for field_name in ['amount_total', 'total_amount', 'amount', 'total']:
            if hasattr(self, field_name):
                amount = getattr(self, field_name)
                if amount:
                    # Try to get currency
                    currency = None
                    for curr_field in ['currency_id', 'company_currency_id']:
                        if hasattr(self, curr_field):
                            currency = getattr(self, curr_field)
                            break
                    
                    if currency:
                        return f"{amount:,.2f} {currency.name}"
                    return f"{amount:,.2f}"
        return None

    def _get_line_approval_message(self, portal_url):
        """
        Build the LINE message content.
        Override this method to customize the message.
        
        Args:
            portal_url: The portal URL for approval
            
        Returns:
            str: LINE message content
        """
        self.ensure_one()
        doc_name = self._get_line_approval_document_name()
        amount = self._get_line_approval_amount()
        
        message_lines = [
            "📄 Document awaiting approval",
            f"Ref: {doc_name}",
        ]
        
        if amount:
            message_lines.append(f"Amount: {amount}")
        
        message_lines.extend([
            "",
            "👉 Review & approve:",
            portal_url,
        ])
        
        return "\n".join(message_lines)

    def action_send_line_approval_request(self, raise_exception=True):
        """
        Main action to send LINE approval request.
        This method:
        1. Validates the approver has a LINE ID
        2. Generates a secure token
        3. Builds the portal URL
        4. Sends the LINE message
        5. Logs the action to chatter and audit trail
        
        Args:
            raise_exception (bool): If True, raise UserError on failure. If False, log error and return False.
        """
        self.ensure_one()
        
        # Get approver
        approver = self._get_line_approval_approver()
        if not approver:
            if raise_exception:
                raise UserError(_("No approver defined for this document. Please set an approver first."))
            else:
                 _logger.warning("LINE Notification: No approver defined for %s %s", self._name, self.id)
                 return False
        
        # Check LINE user ID
        if not approver.line_user_id or not approver.line_user_id.strip():
            msg = _(
                "Approver '%s' does not have a LINE User ID configured. "
                "Please add their LINE ID in their user profile."
            ) % approver.name
            if raise_exception:
                raise UserError(msg)
            else:
                _logger.warning("LINE Notification: %s", msg)
                return False
        
        # Generate token
        doc_name = self._get_line_approval_document_name()
        token = self.env['approval.token'].generate_token(
            res_model=self._name,
            res_id=self.id,
            approver_id=approver.id,
            res_name=doc_name,
            line_user_id=approver.line_user_id,
        )
        
        # Get portal URL
        portal_url = token.get_portal_url()
        
        # Build message
        message = self._get_line_approval_message(portal_url)
        
        # Send LINE message
        line_service = self.env['line.api.service']
        try:
            line_service.send_push_message(approver.line_user_id, message)
        except Exception as e:
            # Log the error
            self.env['approval.audit.log'].log_action(
                res_model=self._name,
                res_id=self.id,
                action='notification_sent',
                approver_id=approver.id,
                line_user_id=approver.line_user_id,
                token_id=token.id,
                token_value=token.token,
                res_name=doc_name,
                notes=f"Failed: {str(e)}",
            )
            msg = _("Failed to send LINE message: %s") % str(e)
            if raise_exception:
                raise UserError(msg)
            else:
                 _logger.error("LINE Notification Error: %s", msg)
                 # Log to chatter as well for visibility
                 if hasattr(self, 'message_post'):
                     self.message_post(body=f"⚠️ {msg}")
                 return False
        
        # Update document
        self.write({
            'line_notification_sent': True,
            'line_notification_datetime': fields.Datetime.now(),
            'approval_token_id': token.id,
        })
        
        # Log to audit trail
        self.env['approval.audit.log'].log_action(
            res_model=self._name,
            res_id=self.id,
            action='notification_sent',
            approver_id=approver.id,
            line_user_id=approver.line_user_id,
            token_id=token.id,
            token_value=token.token,
            res_name=doc_name,
            notes="LINE notification sent successfully",
        )
        
        # Log to chatter if available
        if hasattr(self, 'message_post'):
            self.message_post(
                body=_("LINE approval request sent to %s") % approver.name,
                message_type='notification',
            )
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Success"),
                'message': _("LINE approval request sent to %s") % approver.name,
                'type': 'success',
                'sticky': False,
            }
        }

    def action_approve(self):
        """
        Approve the document.
        Override this method in your model to implement approval logic.
        """
        self.ensure_one()
        raise UserError(_(
            "The action_approve() method must be implemented in the model '%s'."
        ) % self._name)

    def action_reject(self):
        """
        Reject the document.
        Override this method in your model to implement rejection logic.
        """
        self.ensure_one()
        raise UserError(_(
            "The action_reject() method must be implemented in the model '%s'."
        ) % self._name)

    def _invalidate_approval_token(self, action):
        """
        Invalidate the approval token after action.
        
        Args:
            action: 'approved' or 'rejected'
        """
        self.ensure_one()
        if self.approval_token_id and self.approval_token_id.state == 'active':
            self.approval_token_id.mark_as_used(action)
