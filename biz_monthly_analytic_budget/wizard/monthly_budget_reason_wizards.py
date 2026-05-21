# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.addons.biz_monthly_analytic_budget.models.budget_utils import find_active_monthly_plan

class MonthlyBudgetRequestReasonWizard(models.TransientModel):
    _name = 'monthly.budget.request.reason.wizard'
    _description = 'Monthly Budget Request Reason Wizard'

    document_type = fields.Selection([
        ('pr', 'Purchase Requisition (PR)'),
        ('po', 'Purchase Order (PO)'),
        ('bill', 'Vendor Bill'),
    ], string='Document Type', required=True)
    
    ref_id = fields.Integer(string='Document ID', required=True)
    budget_line_names = fields.Char(string='Budget Analytic Lines')
    amount_requested = fields.Float(string='Document Amount', help='ยอดรวมของเอกสารจริง (untaxed)')
    amount_analytic = fields.Float(string='Analytic Amount', help='ยอดที่กระจายไป analytic accounts (อาจต่างจาก Document Amount ถ้ามีหลาย analytic หรือ distribution ไม่ครบ)')
    amount_used = fields.Float(string='Already Used')
    amount_reserved = fields.Float(string='Already Reserved')
    amount_limit = fields.Float(string='Budget Limit')
    amount_overage = fields.Float(string='Over by')
    # Pass the active plan so auto-approve threshold can be evaluated
    plan_id = fields.Many2one('monthly.budget.plan', string='Budget Plan')
    
    reason = fields.Text(string='Reason', required=True, help="เหตุผลในการขอเพิ่มงบประมาณชั่วคราว")

    def action_submit_request(self):
        self.ensure_one()
        ApprovalReq = self.env['buz.monthly.budget.approval.request']

        ref_field_map = {
            'pr': 'ref_pr_id',
            'po': 'ref_po_id',
            'bill': 'ref_bill_id',
        }
        ref_field = ref_field_map.get(self.document_type, 'ref_po_id')

        req = ApprovalReq._get_or_create_pending_request(
            document_type=self.document_type,
            ref_field=ref_field,
            ref_id=self.ref_id,
            budget_line=False,  # Multiple analytics — store names in budget_line_name
            plan_id=self.plan_id.id if self.plan_id else False,
            amount_requested=self.amount_requested,
            amount_analytic=self.amount_analytic,
            amount_used=self.amount_used,
            amount_reserved=self.amount_reserved,
            amount_limit=self.amount_limit,
            amount_overage=self.amount_overage,
        )

        if self.budget_line_names:
            req.budget_line_name = self.budget_line_names

        # Set the reason
        req.reason = self.reason

        # Notify
        req._notify_budget_managers()

        # Post to source document chatter
        model_map = {
            'pr': 'employee.purchase.requisition',
            'po': 'purchase.order',
            'bill': 'account.move',
        }
        doc = self.env[model_map[self.document_type]].browse(self.ref_id)
        if doc.exists():
            doc.message_post(
                body=_(
                    '<strong>Monthly Budget Approval Request Submitted</strong><br/>'
                    'Request: <a href="/web#id=%s&model=buz.monthly.budget.approval.request">%s</a><br/>'
                    'Reason: %s<br/>'
                    'Status: Pending Approval from Budget Manager'
                ) % (req.id, req.name, self.reason),
            )

        return {
            'type': 'ir.actions.act_window',
            'name': _('Monthly Budget Approval Request'),
            'res_model': 'buz.monthly.budget.approval.request',
            'view_mode': 'form',
            'res_id': req.id,
            'target': 'current',
        }


class MonthlyBudgetApprovalReasonWizard(models.TransientModel):
    _name = 'monthly.budget.approval.reason.wizard'
    _description = 'Monthly Budget Approval Reason Wizard'

    request_id = fields.Many2one('buz.monthly.budget.approval.request', string='Request', required=True)
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
