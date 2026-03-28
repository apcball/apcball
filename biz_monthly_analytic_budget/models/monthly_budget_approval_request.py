# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class BuzMonthlyBudgetApprovalRequest(models.Model):
    _name = 'buz.monthly.budget.approval.request'
    _description = 'Monthly Budget Approval Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
    )
    document_type = fields.Selection([
        ('pr', 'Purchase Requisition (PR)'),
        ('po', 'Purchase Order (PO)'),
    ], string='Document Type', required=True, tracking=True)

    ref_pr_id = fields.Many2one(
        'employee.purchase.requisition',
        string='Purchase Requisition',
        ondelete='cascade',
        index=True,
    )
    ref_po_id = fields.Many2one(
        'purchase.order',
        string='Purchase Order',
        ondelete='cascade',
        index=True,
    )

    budget_line_id = fields.Many2one(
        'monthly.budget.line',
        string='Budget Line',
        ondelete='set null',
    )
    budget_line_name = fields.Char(
        string='Budget Line Name',
        help='Stored name in case budget line is removed',
    )
    amount_limit = fields.Float(string='Budget Limit', tracking=True)
    amount_used = fields.Float(string='Already Used', tracking=True)
    amount_reserved = fields.Float(string='Already Reserved', tracking=True)
    amount_requested = fields.Float(string='Document Amount', tracking=True)
    amount_overage = fields.Float(string='Over by', tracking=True)

    reason = fields.Text(
        string='Requester Reason',
        help='Reason why this budget excess should be temporarily approved',
    )
    note = fields.Text(
        string='Approver Note',
        help='Reason for approval or rejection',
    )

    state = fields.Selection([
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='pending', tracking=True, copy=False)

    requester_id = fields.Many2one(
        'res.users',
        string='Requested By',
        default=lambda self: self.env.uid,
        readonly=True,
        tracking=True,
    )
    approver_id = fields.Many2one(
        'res.users',
        string='Processed By',
        readonly=True,
        tracking=True,
    )
    approved_date = fields.Datetime(
        string='Processed Date',
        readonly=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
    )

    document_ref = fields.Char(
        string='Document',
        compute='_compute_document_ref',
    )

    @api.depends('ref_pr_id', 'ref_po_id', 'document_type')
    def _compute_document_ref(self):
        for rec in self:
            if rec.document_type == 'pr' and rec.ref_pr_id:
                rec.document_ref = rec.ref_pr_id.name
            elif rec.document_type == 'po' and rec.ref_po_id:
                rec.document_ref = rec.ref_po_id.name
            else:
                rec.document_ref = ''

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'buz.monthly.budget.approval.request'
                ) or _('New')
        
        records = super().create(vals_list)
        
        # ── Feature 5: Auto-Approve Threshold ────────────────────────
        for rec in records:
            if rec.state == 'pending' and rec.budget_line_id:
                plan = rec.budget_line_id.plan_id
                auto_approve = False
                
                # Check absolute amount threshold
                if plan.auto_approve_threshold > 0 and rec.amount_overage <= plan.auto_approve_threshold:
                    auto_approve = True
                
                # Check percentage threshold
                if not auto_approve and plan.auto_approve_pct > 0 and rec.amount_limit > 0:
                    overage_pct = (rec.amount_overage / rec.amount_limit) * 100.0
                    if overage_pct <= plan.auto_approve_pct:
                        auto_approve = True
                        
                if auto_approve:
                    # using SUPERUSER_ID for auto-approval
                    rec.write({
                        'state': 'approved',
                        'approver_id': self.env.ref('base.user_root').id,
                        'approved_date': fields.Datetime.now(),
                        'note': _('Auto-approved (within threshold)'),
                    })
                    rec.message_post(
                        body=_('<strong>✅ Auto-Approved</strong><br/>'
                               'Overage is within plan threshold.<br/>'
                               'Note: %s') % rec.note,
                    )
                    rec._notify_requester('approved')
        
        return records

    def action_approve(self):
        self.ensure_one()
        # Ensure only budget manager can approve
        # Using the monthly module budget manager group
        if not self.env.user.has_group('biz_monthly_analytic_budget.group_monthly_budget_manager'):
            raise UserError(_('Only Monthly Budget Managers can approve budget requests.'))
        if self.state != 'pending':
            raise UserError(_('Only pending requests can be approved.'))
            
        return {
            'name': _('Approve Budget Request'),
            'type': 'ir.actions.act_window',
            'res_model': 'monthly.budget.approval.reason.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_request_id': self.id,
                'default_action_type': 'approve',
            }
        }

    def action_reject(self):
        self.ensure_one()
        if not self.env.user.has_group('biz_monthly_analytic_budget.group_monthly_budget_manager'):
            raise UserError(_('Only Monthly Budget Managers can reject budget requests.'))
        if self.state != 'pending':
            raise UserError(_('Only pending requests can be rejected.'))
            
        return {
            'name': _('Reject Budget Request'),
            'type': 'ir.actions.act_window',
            'res_model': 'monthly.budget.approval.reason.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_request_id': self.id,
                'default_action_type': 'reject',
            }
        }

    def _do_approve(self):
        for rec in self:
            rec.write({
                'state': 'approved',
                'approver_id': self.env.uid,
                'approved_date': fields.Datetime.now(),
            })
            rec.message_post(
                body=_(
                    '<strong>✅ Budget Approved</strong><br/>'
                    'Approved by: %s<br/>'
                    'Note: %s'
                ) % (self.env.user.name, rec.note or '-'),
            )
            rec._notify_requester('approved')

    def _do_reject(self):
        for rec in self:
            if not rec.note:
                raise ValidationError(_('Please provide a rejection reason.'))
            rec.write({
                'state': 'rejected',
                'approver_id': self.env.uid,
                'approved_date': fields.Datetime.now(),
            })
            rec.message_post(
                body=_(
                    '<strong>❌ Budget Request Rejected</strong><br/>'
                    'Rejected by: %s<br/>'
                    'Reason: %s'
                ) % (self.env.user.name, rec.note),
            )
            rec._notify_requester('rejected')

    def action_cancel(self):
        for rec in self:
            if rec.state not in ('pending',):
                raise UserError(_('Only pending requests can be cancelled.'))
            rec.state = 'cancelled'

    def _notify_requester(self, decision):
        self.ensure_one()
        if not self.requester_id.partner_id:
            return
        body = _(
            'Your Monthly Budget Approval Request <strong>%s</strong> for document <strong>%s</strong> '
            'has been <strong>%s</strong>.'
        ) % (self.name, self.document_ref, decision.upper())
        self.message_post(
            body=body,
            partner_ids=self.requester_id.partner_id.ids,
        )

    def _notify_budget_managers(self):
        self.ensure_one()
        # In monthly we don't necessarily have a predefined template.
        # Fallback to simple chatter message to budget manager group if needed.
        # However, they might want an email template similar to weekly.
        manager_group = self.env.ref(
            'biz_monthly_analytic_budget.group_monthly_budget_manager', raise_if_not_found=False
        )
        if manager_group:
            managers = manager_group.users
            if managers:
                self.message_post(
                    body=_('A new Monthly Budget Approval Request has been created and is waiting for your approval.'),
                    partner_ids=managers.mapped('partner_id').ids,
                )

    @api.model
    def _get_or_create_pending_request(self, document_type, ref_field, ref_id,
                                        budget_line, amount_requested,
                                        amount_used, amount_reserved,
                                        amount_limit, amount_overage):
        domain = [
            ('document_type', '=', document_type),
            (ref_field, '=', ref_id),
            ('state', '=', 'pending'),
        ]
        existing = self.search(domain, limit=1)
        if existing:
            return existing

        vals = {
            'document_type': document_type,
            ref_field: ref_id,
            'budget_line_id': budget_line.id if budget_line else False,
            'budget_line_name': budget_line.display_name if budget_line else 'Multiple/Various',
            'amount_limit': amount_limit,
            'amount_used': amount_used,
            'amount_reserved': amount_reserved,
            'amount_requested': amount_requested,
            'amount_overage': amount_overage,
            'requester_id': self.env.uid,
            'company_id': self.env.company.id,
        }
        return self.create(vals)
