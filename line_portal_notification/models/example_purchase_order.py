# -*- coding: utf-8 -*-
"""
Example: Using LINE Approval Mixin with Purchase Order
=======================================================

This file demonstrates how to inherit the line.approval.mixin
in your own models to add LINE approval functionality.

To use this example:
1. Add 'purchase' to the depends in __manifest__.py
2. Import this file in models/__init__.py

Example for other models:
-------------------------
class YourModel(models.Model):
    _name = 'your.model'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'line.approval.mixin']
    
    approver_id = fields.Many2one('res.users', string='Approver')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('waiting_approval', 'Waiting Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ])
    
    def _get_line_approval_approver(self):
        return self.approver_id
    
    def action_approve(self):
        self.state = 'approved'
        self._invalidate_approval_token('approved')
    
    def action_reject(self):
        self.state = 'rejected'
        self._invalidate_approval_token('rejected')
"""

from odoo import api, fields, models, _


# Uncomment below to enable Purchase Order LINE approval
# Make sure to add 'purchase' to depends in __manifest__.py

# class PurchaseOrderLineApproval(models.Model):
#     _inherit = ['purchase.order', 'line.approval.mixin']
#     _name = 'purchase.order'
#
#     def _get_line_approval_approver(self):
#         """Return the approver for this purchase order."""
#         self.ensure_one()
#         # Example: Use the manager of the user who created the PO
#         if self.user_id and self.user_id.employee_id and self.user_id.employee_id.parent_id:
#             return self.user_id.employee_id.parent_id.user_id
#         # Fallback to a specific user or raise an error
#         return False
#
#     def _get_line_approval_document_name(self):
#         """Return the document reference."""
#         self.ensure_one()
#         return self.name
#
#     def _get_line_approval_amount(self):
#         """Return formatted amount."""
#         self.ensure_one()
#         return f"{self.amount_total:,.2f} {self.currency_id.name}"
#
#     def action_approve(self):
#         """Approve the purchase order."""
#         self.ensure_one()
#         self.button_confirm()  # Standard PO confirmation
#         self._invalidate_approval_token('approved')
#
#     def action_reject(self):
#         """Reject the purchase order."""
#         self.ensure_one()
#         self.button_cancel()  # Standard PO cancellation
#         self._invalidate_approval_token('rejected')
