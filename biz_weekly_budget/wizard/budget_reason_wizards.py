# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError

class BudgetRequestReasonWizard(models.TransientModel):
    _name = 'budget.request.reason.wizard'
    _description = 'Budget Request Reason Wizard'

    document_type = fields.Selection([
        ('pr', 'Purchase Requisition (PR)'),
        ('mr', 'Material Requisition (MR)'),
        ('po', 'Purchase Order (PO)'),
    ], string='Document Type', required=True)
    
    ref_id = fields.Integer(string='Document ID', required=True)
    budget_allocation_id = fields.Many2one('monthly.budget.allocation', string='Budget Allocation')
    amount_requested = fields.Float(string='Document Amount')
    amount_used = fields.Float(string='Already Used')
    amount_reserved = fields.Float(string='Already Reserved')
    amount_limit = fields.Float(string='Budget Limit')
    amount_overage = fields.Float(string='Over by')
    
    reason = fields.Text(string='Reason', required=True, help="เหตุผลในการขอเพิ่มงบประมาณชั่วคราว")

    def action_submit_request(self):
        self.ensure_one()
        ApprovalReq = self.env['buz.budget.approval.request']
        
        ref_field = 'ref_pr_id'
        if self.document_type == 'mr':
            ref_field = 'ref_mr_id'
        elif self.document_type == 'po':
            ref_field = 'ref_po_id'

        req = ApprovalReq._get_or_create_pending_request(
            document_type=self.document_type,
            ref_field=ref_field,
            ref_id=self.ref_id,
            budget_allocation=self.budget_allocation_id,
            amount_requested=self.amount_requested,
            amount_used=self.amount_used,
            amount_reserved=self.amount_reserved,
            amount_limit=self.amount_limit,
            amount_overage=self.amount_overage,
        )
        
        # Set the reason
        req.reason = self.reason

        # Notify
        req._notify_budget_managers()

        # Post to source document chatter
        model_map = {
            'pr': 'employee.purchase.requisition',
            'mr': 'material.requisition',
            'po': 'purchase.order'
        }
        doc = self.env[model_map[self.document_type]].browse(self.ref_id)
        if doc.exists():
            doc.message_post(
                body=_(
                    '<strong>Budget Approval Request Submitted</strong><br/>'
                    'Request: <a href="/web#id=%s&model=buz.budget.approval.request">%s</a><br/>'
                    'Reason: %s<br/>'
                    'Status: Pending Approval from Budget Manager'
                ) % (req.id, req.name, self.reason),
            )

        return {
            'type': 'ir.actions.act_window',
            'name': _('Budget Approval Request'),
            'res_model': 'buz.budget.approval.request',
            'view_mode': 'form',
            'res_id': req.id,
            'target': 'current',
        }


class BudgetApprovalReasonWizard(models.TransientModel):
    _name = 'budget.approval.reason.wizard'
    _description = 'Budget Approval Reason Wizard'

    request_id = fields.Many2one('buz.budget.approval.request', string='Request', required=True)
    action_type = fields.Selection([
        ('approve', 'Approve'),
        ('reject', 'Reject')
    ], string='Action', required=True)
    
    note = fields.Text(string='Note', required=True, help="เหตุผลในการอนุมัติ หรือปฏิเสธ")

    def action_confirm(self):
        self.ensure_one()
        self.request_id.note = self.note
        if self.action_type == 'approve':
            self.request_id._do_approve()
        elif self.action_type == 'reject':
            self.request_id._do_reject()
