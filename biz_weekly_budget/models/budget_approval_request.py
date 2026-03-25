# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class BuzBudgetApprovalRequest(models.Model):
    _name = 'buz.budget.approval.request'
    _description = 'Budget Approval Request'
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
        ('mr', 'Material Requisition (MR)'),
        ('po', 'Purchase Order (PO)'),
    ], string='Document Type', required=True, tracking=True)

    ref_pr_id = fields.Many2one(
        'employee.purchase.requisition',
        string='Purchase Requisition',
        ondelete='cascade',
        index=True,
    )
    ref_mr_id = fields.Many2one(
        'material.requisition',
        string='Material Requisition',
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
        'weekly.budget.line',
        string='Budget Week',
        ondelete='set null',
    )
    budget_line_name = fields.Char(
        string='Budget Week Name',
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

    # ── Computed display name of related document ─────────────────────────────
    document_ref = fields.Char(
        string='Document',
        compute='_compute_document_ref',
    )

    @api.depends('ref_pr_id', 'ref_mr_id', 'ref_po_id', 'document_type')
    def _compute_document_ref(self):
        for rec in self:
            if rec.document_type == 'pr' and rec.ref_pr_id:
                rec.document_ref = rec.ref_pr_id.name
            elif rec.document_type == 'mr' and rec.ref_mr_id:
                rec.document_ref = rec.ref_mr_id.name
            elif rec.document_type == 'po' and rec.ref_po_id:
                rec.document_ref = rec.ref_po_id.name
            else:
                rec.document_ref = ''

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'buz.budget.approval.request'
                ) or _('New')
        return super().create(vals_list)

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_approve(self):
        self.ensure_one()
        if not self.env.user.has_group('biz_weekly_budget.group_budget_manager'):
            raise UserError(_('Only Budget Managers can approve budget requests.'))
        if self.state != 'pending':
            raise UserError(_('Only pending requests can be approved.'))
            
        return {
            'name': _('Approve Budget Request'),
            'type': 'ir.actions.act_window',
            'res_model': 'budget.approval.reason.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_request_id': self.id,
                'default_action_type': 'approve',
            }
        }

    def action_reject(self):
        self.ensure_one()
        if not self.env.user.has_group('biz_weekly_budget.group_budget_manager'):
            raise UserError(_('Only Budget Managers can reject budget requests.'))
        if self.state != 'pending':
            raise UserError(_('Only pending requests can be rejected.'))
            
        return {
            'name': _('Reject Budget Request'),
            'type': 'ir.actions.act_window',
            'res_model': 'budget.approval.reason.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_request_id': self.id,
                'default_action_type': 'reject',
            }
        }

    def _do_approve(self):
        """Budget Manager approves the request (called from wizard)."""
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
        """Budget Manager rejects the request (called from wizard)."""
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
        """Requester cancels a pending request."""
        for rec in self:
            if rec.state not in ('pending',):
                raise UserError(_('Only pending requests can be cancelled.'))
            rec.state = 'cancelled'

    def _notify_requester(self, decision):
        """Send a chatter message to the requester when the request is processed."""
        self.ensure_one()
        if not self.requester_id.partner_id:
            return
        body = _(
            'Your Budget Approval Request <strong>%s</strong> for document <strong>%s</strong> '
            'has been <strong>%s</strong>.'
        ) % (self.name, self.document_ref, decision.upper())
        self.message_post(
            body=body,
            partner_ids=self.requester_id.partner_id.ids,
        )

    def _notify_budget_managers(self):
        """Send email to all budget managers about this approval request."""
        self.ensure_one()
        template = self.env.ref(
            'biz_weekly_budget.mail_template_budget_approval_request',
            raise_if_not_found=False,
        )
        if not template:
            return

        manager_group = self.env.ref(
            'biz_weekly_budget.group_budget_manager', raise_if_not_found=False
        )
        if not manager_group:
            return

        managers = manager_group.users
        for manager in managers:
            if not manager.email:
                continue
            try:
                template.with_context(
                    manager_email=manager.email,
                ).send_mail(self.id, force_send=False)
            except Exception as e:
                _logger.warning(
                    'Failed to send budget approval request email to %s: %s',
                    manager.email, str(e)
                )

    @api.model
    def _get_or_create_pending_request(self, document_type, ref_field, ref_id,
                                        budget_line, amount_requested,
                                        amount_used, amount_reserved,
                                        amount_limit, amount_overage):
        """
        Return an existing pending request for this document, or create a new one.
        Called from PR/MR/PO models when budget is exceeded.
        """
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
            'budget_line_name': budget_line.name if budget_line else '',
            'amount_limit': amount_limit,
            'amount_used': amount_used,
            'amount_reserved': amount_reserved,
            'amount_requested': amount_requested,
            'amount_overage': amount_overage,
            'requester_id': self.env.uid,
            'company_id': self.env.company.id,
        }
        return self.create(vals)
