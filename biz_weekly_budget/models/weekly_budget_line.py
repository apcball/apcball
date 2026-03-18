# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class WeeklyBudgetLine(models.Model):
    _name = 'weekly.budget.line'
    _description = 'Weekly Budget Line'
    _order = 'date_from asc'

    plan_id = fields.Many2one(
        'weekly.budget.plan',
        string='Budget Plan',
        required=True,
        ondelete='cascade',
        index=True,
    )
    name = fields.Char(string='Week Label', required=True)
    week_number = fields.Integer(string='Week #')
    date_from = fields.Date(string='Date From', required=True, index=True)
    date_to = fields.Date(string='Date To', required=True, index=True)
    amount_limit = fields.Float(string='Budget Limit', required=True)
    amount_used = fields.Float(
        string='Used Amount',
        compute='_compute_amount_used',
        store=True,
    )
    amount_reserved = fields.Float(
        string='Reserved Amount',
        compute='_compute_amount_reserved',
        store=True,
        help='Total tentative budget reserved from non-draft PRs and standalone RFQs.',
    )
    amount_available = fields.Float(
        string='Available',
        compute='_compute_remaining',
        store=True,
        help='Budget Limit minus Used and Reserved amounts.',
    )
    amount_remaining = fields.Float(
        string='Remaining (vs Used)',
        compute='_compute_remaining',
        store=True,
    )
    usage_percentage = fields.Float(
        string='Usage %',
        compute='_compute_remaining',
        store=True,
    )
    status = fields.Selection([
        ('normal', 'Normal'),
        ('exceeded', 'Exceeded'),
    ], string='Status', compute='_compute_remaining', store=True)

    currency_id = fields.Many2one(
        related='plan_id.currency_id',
        string='Currency',
        store=True,
    )
    company_id = fields.Many2one(
        related='plan_id.company_id',
        string='Company',
        store=True,
    )
    all_companies = fields.Boolean(
        related='plan_id.all_companies',
        string='All Companies',
        store=True,
    )
    plan_state = fields.Selection(
        related='plan_id.state',
        string='Plan Status',
        store=True,
    )

    # History tracking
    history_ids = fields.One2many(
        'weekly.budget.line.history',
        'line_id',
        string='Adjustment History',
    )

    def _get_company_domain(self):
        """Return company domain filter for this budget line."""
        if self.plan_id.all_companies:
            return []
        elif self.plan_id.company_id:
            return [('company_id', '=', self.plan_id.company_id.id)]
        return []

    @api.depends('date_from', 'date_to', 'plan_id.company_id',
                 'plan_id.all_companies', 'plan_id.state')
    def _compute_amount_used(self):
        """Compute total confirmed PO amount for this week's date range."""
        for line in self:
            if not line.date_from or not line.date_to:
                line.amount_used = 0.0
                continue

            # Find PO lines where date_planned falls within this week
            po_line_domain = [
                ('order_id.state', 'in', ['purchase', 'done']),
                ('date_planned', '>=', fields.Datetime.to_datetime(line.date_from)),
                ('date_planned', '<=', fields.Datetime.to_datetime(
                    line.date_to).replace(hour=23, minute=59, second=59)),
            ]

            if line.plan_id.all_companies:
                pass
            elif line.plan_id.company_id:
                po_line_domain.append(
                    ('order_id.company_id', '=', line.plan_id.company_id.id)
                )

            po_lines = self.env['purchase.order.line'].sudo().search(po_line_domain)
            line.amount_used = sum(po_lines.mapped('price_subtotal'))

    @api.depends('date_from', 'date_to', 'plan_id.company_id',
                 'plan_id.all_companies', 'plan_id.state')
    def _compute_amount_reserved(self):
        """
        Compute total budget reserved from:
          1. Non-draft PRs whose deadline/request_date falls in week
             → SKIP if a confirmed PO already links to that PR
             (PR sets po.requisition_order = pr.name and po.pr_number = pr.name)
          2. Draft POs (RFQs) NOT linked to any active PR
             (to prevent double-counting while in RFQ stage)
        When a PR is converted to a confirmed PO, the PO amount moves
        to amount_used, so the reservation must disappear.
        """
        for line in self:
            if not line.date_from or not line.date_to:
                line.amount_reserved = 0.0
                continue

            date_from = line.date_from
            date_to = line.date_to
            company_id = line.plan_id.company_id.id if not line.plan_id.all_companies else False

            # ── Pre-fetch confirmed POs for exclusion ──────────────────────
            confirmed_po_domain = [('state', 'in', ['purchase', 'done'])]
            if company_id:
                confirmed_po_domain.append(('company_id', '=', company_id))

            confirmed_pos = self.env['purchase.order'].sudo().search(confirmed_po_domain)

            # PR names that appear on confirmed POs
            # PR sets po.requisition_order = pr.name AND po.pr_number = pr.name
            confirmed_pr_names = set()
            for po in confirmed_pos:
                req_order = getattr(po, 'requisition_order', False)
                pr_number = getattr(po, 'pr_number', False)
                if req_order:
                    confirmed_pr_names.add(req_order.strip())
                if pr_number:
                    confirmed_pr_names.add(pr_number.strip())

            # ── 1. Non-draft PRs ────────────────────────────────────────────
            pr_domain = [
                ('state', '!=', 'draft'),
                '|',
                '&',
                ('requisition_deadline', '>=', date_from),
                ('requisition_deadline', '<=', date_to),
                '&',
                ('request_date', '>=', date_from),
                ('request_date', '<=', date_to),
            ]
            if company_id:
                pr_domain.append(('company_id', '=', company_id))

            prs = self.env['employee.purchase.requisition'].sudo().search(pr_domain)

            pr_amount = 0.0
            active_pr_names = set()
            for pr in prs:
                # Skip PRs already converted to a confirmed PO
                if pr.name in confirmed_pr_names:
                    continue
                pr_amount += sum(pr.requisition_order_ids.mapped('price_subtotal'))
                active_pr_names.add(pr.name)

            # ── 2. Standalone RFQs (draft POs not linked to any active PR) ────
            rfq_line_domain = [
                ('order_id.state', '=', 'draft'),
                ('date_planned', '>=', fields.Datetime.to_datetime(date_from)),
                ('date_planned', '<=', fields.Datetime.to_datetime(
                    date_to).replace(hour=23, minute=59, second=59)),
            ]
            if company_id:
                rfq_line_domain.append(('order_id.company_id', '=', company_id))

            rfq_lines = self.env['purchase.order.line'].sudo().search(rfq_line_domain)

            rfq_amount = 0.0
            seen_rfq_ids = set()
            for rfq_line in rfq_lines:
                po = rfq_line.order_id
                if po.id in seen_rfq_ids:
                    continue
                seen_rfq_ids.add(po.id)

                # Skip if linked to an active PR:
                # PR sets po.requisition_order and po.pr_number to pr.name
                req_order = (getattr(po, 'requisition_order', '') or '').strip()
                pr_number = (getattr(po, 'pr_number', '') or '').strip()
                if req_order in active_pr_names or pr_number in active_pr_names:
                    continue

                # Also skip if po.origin contains an active PR name
                origin = (po.origin or '').strip()
                if any(pr_name and pr_name in origin for pr_name in active_pr_names):
                    continue

                rfq_amount += rfq_line.price_subtotal

            line.amount_reserved = pr_amount + rfq_amount



    @api.depends('amount_limit', 'amount_used', 'amount_reserved')
    def _compute_remaining(self):
        for line in self:
            line.amount_remaining = line.amount_limit - line.amount_used
            line.amount_available = line.amount_limit - line.amount_used - line.amount_reserved
            line.usage_percentage = (
                (line.amount_used / line.amount_limit * 100)
                if line.amount_limit else 0.0
            )
            line.status = 'exceeded' if line.amount_used > line.amount_limit else 'normal'

    def action_adjust_budget(self):
        """Open the budget adjustment wizard."""
        self.ensure_one()
        return {
            'name': _('Adjust Budget'),
            'type': 'ir.actions.act_window',
            'res_model': 'budget.adjustment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_line_id': self.id,
                'default_current_amount': self.amount_limit,
            },
        }

    def _invalidate_reserved(self):
        """Force recompute of amount_reserved for budget lines covering this date range."""
        self.invalidate_recordset(['amount_reserved'])
        self._compute_amount_reserved()


class WeeklyBudgetLineHistory(models.Model):
    _name = 'weekly.budget.line.history'
    _description = 'Budget Line Adjustment History'
    _order = 'create_date desc'

    line_id = fields.Many2one(
        'weekly.budget.line',
        string='Budget Line',
        required=True,
        ondelete='cascade',
    )
    user_id = fields.Many2one(
        'res.users',
        string='Adjusted By',
        default=lambda self: self.env.uid,
        readonly=True,
    )
    date = fields.Datetime(
        string='Date',
        default=fields.Datetime.now,
        readonly=True,
    )
    old_amount = fields.Float(string='Previous Amount', readonly=True)
    new_amount = fields.Float(string='New Amount', readonly=True)
    reason = fields.Text(string='Reason', readonly=True)
