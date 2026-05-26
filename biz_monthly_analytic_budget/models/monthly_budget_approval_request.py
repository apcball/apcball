# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

from .budget_utils import (
    extract_analytic_amounts,
    get_first_plan_from_groups,
    split_analytic_totals_by_plan,
)

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
        ('bill', 'Vendor Bill (Bill)'),
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
    ref_bill_id = fields.Many2one(
        'account.move',
        string='Vendor Bill',
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
    amount_requested = fields.Float(string='Document Amount', tracking=True, help='ยอดรวมของเอกสารจริง (untaxed)')
    amount_analytic = fields.Float(string='Analytic Amount', tracking=True, help='ยอดที่กระจายไป analytic accounts')
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
    plan_id = fields.Many2one(
        'monthly.budget.plan',
        string='Budget Plan',
        ondelete='set null',
        index=True,
        help='Active monthly budget plan at the time of request.',
    )

    document_ref = fields.Char(
        string='Document',
        compute='_compute_document_ref',
    )

    @api.model
    def _ensure_approval_request_sequence(self):
        sequence_code = 'buz.monthly.budget.approval.request'
        sequence = self.env['ir.sequence'].sudo().search([
            ('code', '=', sequence_code),
        ], limit=1)
        if not sequence:
            sequence = self.env['ir.sequence'].sudo().create({
                'name': 'Monthly Budget Approval Request',
                'code': sequence_code,
                'prefix': 'AR/%(year)s/',
                'padding': 5,
                'company_id': False,
            })
        return sequence

    @api.depends('ref_pr_id', 'ref_po_id', 'ref_bill_id', 'document_type')
    def _compute_document_ref(self):
        for rec in self:
            if rec.document_type == 'pr' and rec.ref_pr_id:
                rec.document_ref = rec.ref_pr_id.name
            elif rec.document_type == 'po' and rec.ref_po_id:
                rec.document_ref = rec.ref_po_id.name
            elif rec.document_type == 'bill' and rec.ref_bill_id:
                rec.document_ref = rec.ref_bill_id.name
            else:
                rec.document_ref = ''

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                self._ensure_approval_request_sequence()
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'buz.monthly.budget.approval.request'
                ) or _('New')

        records = super().create(vals_list)

        for rec in records:
            if rec.state == 'pending':
                plan = rec.plan_id or (rec.budget_line_id.plan_id if rec.budget_line_id else False)
                if not plan:
                    continue

                auto_approve = False

                if plan.auto_approve_threshold > 0 and rec.amount_overage <= plan.auto_approve_threshold:
                    auto_approve = True

                if not auto_approve and plan.auto_approve_pct > 0 and rec.amount_limit > 0:
                    overage_pct = (rec.amount_overage / rec.amount_limit) * 100.0
                    if overage_pct <= plan.auto_approve_pct:
                        auto_approve = True

                if auto_approve:
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
            rec._create_rejection_activity_on_source_document()

    def _create_rejection_activity_on_source_document(self):
        """Create a Todo activity on the source document (PR/PO/Bill) so the
        requester sees the rejection reason directly in their document chatter."""
        self.ensure_one()
        doc = False
        if self.document_type == 'pr' and self.ref_pr_id:
            doc = self.ref_pr_id
        elif self.document_type == 'po' and self.ref_po_id:
            doc = self.ref_po_id
        elif self.document_type == 'bill' and self.ref_bill_id:
            doc = self.ref_bill_id
        if not doc:
            return

        ActivityType = self.env['mail.activity.type'].sudo()
        activity_type = ActivityType.search([
            ('name', '=', 'Budget Rejected'),
        ], limit=1)
        if not activity_type:
            activity_type = ActivityType.create({
                'name': 'Budget Rejected',
                'summary': 'Monthly Budget Request Rejected',
                'category': 'default',
                'delay_count': 0,
                'delay_from': 'current',
                'decoration_type': 'warning',
            })

        doc.activity_schedule(
            activity_type_id=activity_type.id,
            user_id=self.requester_id.id or self.env.uid,
            note=_(
                '<strong>Budget Request Rejected</strong><br/>'
                'Reference: %s<br/>'
                'Rejected by: %s<br/>'
                '<strong>Reason:</strong> %s'
            ) % (self.name, self.env.user.name, self.note or '-'),
        )

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

    def _prepare_amounts_from_source_document(self):
        self.ensure_one()
        BudgetLine = self.env['monthly.budget.line']
        AnalyticAccount = self.env['account.analytic.account']

        if self.document_type == 'pr':
            doc = self.ref_pr_id
            if not doc or not doc.payment_date:
                return False, set()
            analytic_totals = {}
            for line in doc.requisition_order_ids:
                for account_id, amount in extract_analytic_amounts(line):
                    analytic_totals[account_id] = analytic_totals.get(account_id, 0.0) + amount
            target_date = doc.payment_date
            document_amount = sum(doc.requisition_order_ids.mapped('price_subtotal'))
            overage_mode = 'analytic'
        elif self.document_type == 'po':
            doc = self.ref_po_id
            if not doc or not doc.payment_date:
                return False, set()
            analytic_totals = {}
            for line in doc.order_line:
                for account_id, amount in extract_analytic_amounts(line):
                    analytic_totals[account_id] = analytic_totals.get(account_id, 0.0) + amount
            target_date = doc.payment_date
            document_amount = doc.amount_untaxed
            overage_mode = 'po'
        elif self.document_type == 'bill':
            doc = self.ref_bill_id
            target_date = doc._get_bill_target_date() if doc else False
            if not doc or not target_date:
                return False, set()
            analytic_totals = {}
            for line in doc.invoice_line_ids:
                for account_id, amount in extract_analytic_amounts(line, BudgetLine):
                    analytic_totals[account_id] = analytic_totals.get(account_id, 0.0) + amount
            document_amount = doc.amount_untaxed
            overage_mode = 'analytic'
        else:
            return False, set()

        grouped_totals, _ignored_totals = split_analytic_totals_by_plan(
            self.env, target_date, doc.company_id.id, analytic_totals,
        )
        if not grouped_totals:
            return False, set()

        analytic_amount = sum(analytic_totals.values())
        limit_amt = 0.0
        used = 0.0
        reserved = 0.0
        budget_line_names = []
        affected_plan_ids = set()

        for plan, plan_totals in grouped_totals:
            affected_plan_ids.add(plan.id)
            has_pr = doc._has_active_source_requisition_for_plan(plan) if self.document_type == 'po' else False
            po_already_reserved = doc._is_counted_in_monthly_budget_reserve(plan) if self.document_type == 'po' else False
            for account_id, amt in plan_totals.items():
                analytic = AnalyticAccount.browse(account_id)
                if not analytic.exists():
                    continue
                bl = BudgetLine._find_budget_line(plan, {'analytic_account_id': account_id}, log_fallback=False)
                if not bl:
                    continue
                limit_amt += bl.budget_amount
                used += bl.used_amount
                if self.document_type == 'po' and not has_pr and not po_already_reserved:
                    reserved += bl.reserved_amount + amt
                else:
                    reserved += bl.reserved_amount
                budget_line_names.append('%s (%s)' % (bl.analytic_account_id.name, plan.name))

        if overage_mode == 'po':
            overage = max(0.0, used + reserved - limit_amt)
        else:
            overage = max(0.0, used + reserved + analytic_amount - limit_amt)

        primary_plan = get_first_plan_from_groups(grouped_totals)
        vals = {
            'amount_requested': document_amount,
            'amount_analytic': analytic_amount,
            'amount_used': used,
            'amount_reserved': reserved,
            'amount_limit': limit_amt,
            'amount_overage': overage,
            'budget_line_name': ', '.join(budget_line_names) or self.budget_line_name,
            'plan_id': primary_plan.id if primary_plan else self.plan_id.id,
        }
        return vals, affected_plan_ids

    def _refresh_amounts_from_source_document(self):
        affected_plan_ids = set()
        for rec in self:
            vals, plan_ids = rec._prepare_amounts_from_source_document()
            if vals:
                rec.write(vals)
            affected_plan_ids.update(plan_ids)
        return affected_plan_ids

    @api.model
    def _get_or_create_pending_request(self, document_type, ref_field, ref_id,
                                        budget_line, amount_requested,
                                        amount_used, amount_reserved,
                                        amount_limit, amount_overage,
                                        amount_analytic=0.0,
                                        plan_id=False):
        domain = [
            ('document_type', '=', document_type),
            (ref_field, '=', ref_id),
            ('state', '=', 'pending'),
        ]
        existing = self.search(domain, limit=1)
        if existing:
            write_vals = {
                'amount_requested': amount_requested,
                'amount_analytic': amount_analytic,
                'amount_used': amount_used,
                'amount_reserved': amount_reserved,
                'amount_limit': amount_limit,
                'amount_overage': amount_overage,
            }
            if existing.name in (False, _('New')):
                self._ensure_approval_request_sequence()
                write_vals['name'] = self.env['ir.sequence'].next_by_code(
                    'buz.monthly.budget.approval.request'
                ) or existing.name
            existing.write(write_vals)
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
            'amount_analytic': amount_analytic,
            'amount_overage': amount_overage,
            'requester_id': self.env.uid,
            'company_id': self.env.company.id,
            'plan_id': plan_id or False,
        }
        return self.create(vals)
