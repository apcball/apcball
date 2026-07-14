# -*- coding: utf-8 -*-
import calendar
import logging
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

from .budget_utils import (
    RESERVED_PR_STATES,
    extract_analytic_amounts,
    filter_analytic_totals_for_plan,
    find_active_monthly_plans,
)

_logger = logging.getLogger(__name__)

_MONTH_SELECTION = [
    ('1',  'มกราคม'),
    ('2',  'กุมภาพันธ์'),
    ('3',  'มีนาคม'),
    ('4',  'เมษายน'),
    ('5',  'พฤษภาคม'),
    ('6',  'มิถุนายน'),
    ('7',  'กรกฎาคม'),
    ('8',  'สิงหาคม'),
    ('9',  'กันยายน'),
    ('10', 'ตุลาคม'),
    ('11', 'พฤศจิกายน'),
    ('12', 'ธันวาคม'),
]


class MonthlyBudgetPlan(models.Model):
    """Monthly Budget Plan — defines total budget for a calendar month."""
    _name = 'monthly.budget.plan'
    _description = 'Monthly Budget Plan'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'year desc, month desc, id desc'
    _rec_name = 'name'

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        default=lambda self: _('New'),
        tracking=True,
    )
    month = fields.Selection(
        selection=_MONTH_SELECTION,
        string='เดือน',
        required=True,
        tracking=True,
    )
    year = fields.Char(
        string='ปี (ค.ศ.)',
        required=True,
        size=4,
        tracking=True,
        default=lambda self: str(fields.Date.today().year),
    )
    date_from = fields.Date(
        string='From',
        compute='_compute_period_dates',
        store=True,
        tracking=True,
    )
    date_to = fields.Date(
        string='To',
        compute='_compute_period_dates',
        store=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    currency_id = fields.Many2one(
        related='company_id.currency_id',
        readonly=True,
        store=True,
    )
    total_budget = fields.Monetary(
        string='Total Budget',
        currency_field='currency_id',
        required=True,
        tracking=True,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
            ('closed', 'Closed'),
        ],
        string='Status',
        default='draft',
        required=True,
        tracking=True,
        copy=False,
    )
    budget_line_ids = fields.One2many(
        'monthly.budget.line',
        'plan_id',
        string='Budget Lines',
        copy=True,
    )

    # ── Feature 1: Budget Rollover ───────────────────────────────
    carry_forward = fields.Boolean(
        string='Carry Forward Surplus',
        default=False,
        help='If checked, the remaining budget will be carried forward to the next month.',
    )
    carry_forward_cap = fields.Float(
        string='Carry Forward Cap (%)',
        default=0.0,
        help='Maximum percentage of the original budget that can be carried forward (0 = unlimited).',
    )
    source_plan_id = fields.Many2one(
        'monthly.budget.plan',
        string='Rolled Over From',
        readonly=True,
    )

    # ── Feature 2: Amendment History ─────────────────────────────
    amendment_ids = fields.One2many(
        'monthly.budget.amendment',
        'plan_id',
        string='Amendments',
    )

    # ── Feature 5: Auto-Approve Threshold ────────────────────────
    auto_approve_threshold = fields.Float(
        string='Auto-Approve Threshold Amount',
        default=0.0,
        help='Budget requests with overage up to this amount will be auto-approved.',
    )
    auto_approve_pct = fields.Float(
        string='Auto-Approve Threshold (%)',
        default=0.0,
        help='Budget requests with overage % up to this value will be auto-approved.',
    )

    # ── computed totals ──────────────────────────────────────────
    
    commitment_count = fields.Integer(
        string='Commitments',
        compute='_compute_commitment_count'
    )

    def _compute_commitment_count(self):
        Commitment = self.env['budget.commitment'].sudo()
        for plan in self:
            count = Commitment.search_count([
                ('budget_source', '=', 'monthly'),
                ('date', '>=', plan.date_from),
                ('date', '<=', plan.date_to),
                ('company_id', '=', plan.company_id.id),
                ('state', 'in', ('reserved', 'used')),
            ])
            plan.commitment_count = count

    def action_view_commitments(self):
        self.ensure_one()
        return {
            'name': _('Budget Commitments (Reserved & Used)'),
            'type': 'ir.actions.act_window',
            'res_model': 'budget.commitment',
            'view_mode': 'list,form',
            'domain': [
                ('budget_source', '=', 'monthly'),
                ('date', '>=', self.date_from),
                ('date', '<=', self.date_to),
                ('company_id', '=', self.company_id.id),
                ('state', 'in', ('reserved', 'used')),
            ],
            'context': {
                'default_budget_source': 'monthly',
                'default_company_id': self.company_id.id,
            }
        }

    allocated_amount = fields.Monetary(
        string='Total Allocated',
        compute='_compute_totals',
        store=False,
        currency_field='currency_id',
    )
    reserved_amount = fields.Monetary(
        string='Total Reserved',
        compute='_compute_totals',
        store=False,
        currency_field='currency_id',
    )
    used_amount = fields.Monetary(
        string='Total Used',
        compute='_compute_totals',
        store=False,
        currency_field='currency_id',
    )
    available_amount = fields.Monetary(
        string='Total Available',
        compute='_compute_totals',
        store=False,
        currency_field='currency_id',
    )
    allocated_percentage = fields.Float(
        string='Allocated (%)',
        compute='_compute_totals',
        store=False,
    )
    carried_amount = fields.Monetary(
        string='Total Carried Forward',
        compute='_compute_totals',
        store=False,
        currency_field='currency_id',
    )

    @api.depends('month', 'year')
    def _compute_period_dates(self):
        # calendar is imported at module level
        for plan in self:
            try:
                m = int(plan.month) if plan.month else 0
                y = int(plan.year) if plan.year else 0
            except (ValueError, TypeError):
                m, y = 0, 0
            if m and y:
                last_day = calendar.monthrange(y, m)[1]
                plan.date_from = fields.Date.from_string('%04d-%02d-01' % (y, m))
                plan.date_to = fields.Date.from_string('%04d-%02d-%02d' % (y, m, last_day))
            else:
                plan.date_from = False
                plan.date_to = False

    @api.depends(
        'budget_line_ids.budget_amount',
        'budget_line_ids.carried_amount',
        'budget_line_ids.reserved_amount',
        'budget_line_ids.used_amount',
        'total_budget',
    )
    def _compute_totals(self):
        for plan in self:
            lines = plan.budget_line_ids
            plan.allocated_amount = sum(lines.mapped('budget_amount'))
            plan.carried_amount = sum(lines.mapped('carried_amount'))
            plan.reserved_amount = sum(lines.mapped('reserved_amount'))
            plan.used_amount = sum(lines.mapped('used_amount'))

            plan.available_amount = (
                plan.total_budget + plan.carried_amount - plan.reserved_amount - plan.used_amount
            )
            plan.allocated_percentage = (
                (plan.allocated_amount / plan.total_budget)
                if plan.total_budget else 0.0
            )

    def _refresh_budget_snapshot(self, refresh_report=False):
        """
        Refresh line-level live balances and plan-level summary fields.

        This is the single place to use after budget-affecting mutations so the
        current transaction sees consistent values immediately.
        """
        self.ensure_one()
        # Clear any cached computed values before recomputing so opened forms
        # do not keep showing stale reserved/used totals after budget changes.
        self.invalidate_recordset([
            'allocated_amount',
            'reserved_amount',
            'used_amount',
            'available_amount',
            'allocated_percentage',
            'carried_amount',
        ])
        self.budget_line_ids.invalidate_recordset([
            'reserved_amount',
            'used_amount',
            'available_amount',
            'utilization_rate',
        ])
        self.budget_line_ids._recompute_line_balance()
        self._compute_totals()
        self.invalidate_recordset([
            'allocated_amount',
            'reserved_amount',
            'used_amount',
            'available_amount',
            'allocated_percentage',
            'carried_amount',
        ])
        if refresh_report:
            try:
                self.env['monthly.budget.report'].refresh_materialized_view()
            except Exception as e:
                _logger.warning(
                    'Could not refresh budget report MV after budget snapshot refresh: %s',
                    e,
            )

    def _filter_plan_analytic_totals(self, analytic_totals):
        """
        Restrict document analytic totals to the analytics defined on this plan.
        """
        self.ensure_one()
        return filter_analytic_totals_for_plan(self, analytic_totals)

    def _sync_existing_pr_reservations(self):
        """Backfill/update reservation commitments for PRs already past Head approval."""
        BudgetLine = self.env['monthly.budget.line']
        Commitment = self.env['budget.commitment'].sudo()
        PurchaseOrder = self.env['purchase.order'].sudo()
        engine = self.env['budget.engine']

        synced_count = 0
        for plan in self:
            if not plan.date_from or not plan.date_to:
                continue

            prs = self.env['employee.purchase.requisition'].sudo().search([
                ('state', 'in', RESERVED_PR_STATES),
                ('payment_date', '>=', plan.date_from),
                ('payment_date', '<=', plan.date_to),
                ('company_id', '=', plan.company_id.id),
            ])
            if not prs:
                continue

            pr_names = [name for name in prs.mapped('name') if name]
            confirmed_pos = PurchaseOrder.search([
                ('state', 'in', ['purchase', 'done']),
                ('company_id', '=', plan.company_id.id),
                '|', '|',
                ('requisition_order', 'in', pr_names),
                ('pr_number', 'in', pr_names),
                ('origin', 'in', pr_names),
            ]) if pr_names else PurchaseOrder.browse()
            confirmed_pr_names = set()
            for po in confirmed_pos:
                for value in (getattr(po, 'requisition_order', '') or '',
                              getattr(po, 'pr_number', '') or '',
                              po.origin or ''):
                    if value:
                        confirmed_pr_names.add(value.strip())

            for pr in prs.filtered(lambda rec: rec.name not in confirmed_pr_names):
                analytic_totals = {}
                for line in pr.requisition_order_ids:
                    for account_id, amount in extract_analytic_amounts(line, BudgetLine):
                        analytic_totals[account_id] = analytic_totals.get(account_id, 0.0) + amount

                analytic_totals, _ignored_totals = plan._filter_plan_analytic_totals(analytic_totals)

                for account_id, amount in analytic_totals.items():
                    if not amount:
                        continue
                    budget_line = BudgetLine._find_budget_line(
                        plan, {'analytic_account_id': account_id}, log_fallback=False
                    )
                    if not budget_line:
                        continue

                    used_commitment = Commitment.search([
                        ('document_model', '=', pr._name),
                        ('document_id', '=', pr.id),
                        ('analytic_account_id', '=', account_id),
                        ('budget_source', '=', 'monthly'),
                        ('state', '=', 'used'),
                    ], limit=1)
                    if used_commitment:
                        continue

                    reserved_commitments = Commitment.search([
                        ('document_model', '=', pr._name),
                        ('document_id', '=', pr.id),
                        ('analytic_account_id', '=', account_id),
                        ('budget_source', '=', 'monthly'),
                        ('state', '=', 'reserved'),
                    ], order='id asc')
                    note = _('Reserved from PR %s - %s') % (
                        pr.name,
                        self.env['account.analytic.account'].sudo().browse(account_id).display_name,
                    )
                    if reserved_commitments:
                        primary = reserved_commitments[0]
                        duplicate_reservations = reserved_commitments - primary
                        if duplicate_reservations:
                            duplicate_reservations.action_release()
                        primary.write({
                            'amount': amount,
                            'date': pr.payment_date,
                            'company_id': pr.company_id.id,
                            'note': note,
                        })
                    else:
                        engine.reserve_budget({
                            'budget_source': 'monthly',
                            'document_model': pr._name,
                            'document_id': pr.id,
                            'amount': amount,
                            'date': pr.payment_date,
                            'company_id': pr.company_id.id,
                            'analytic_account_id': account_id,
                            'note': note,
                        })
                    synced_count += 1

        return synced_count

    def _sync_existing_po_reservations(self):
        """Backfill/update commitments for confirmed POs that already exist.

        Delegates to purchase.order._consume_monthly_analytic_budget() so the
        backfill applies the exact same rules as the live flow: the PO (via its
        PR identity) only reserves the UNBILLED portion of each line, while
        draft/posted bills carry their own commitments. Recreating full-amount
        'used' commitments here double-counted every billed PO.
        """
        PurchaseOrder = self.env['purchase.order'].sudo()
        Commitment = self.env['budget.commitment'].sudo()

        synced_count = 0
        for plan in self:
            if not plan.date_from or not plan.date_to:
                continue

            plan_start = fields.Datetime.to_datetime(plan.date_from)
            plan_end = fields.Datetime.to_datetime(plan.date_to).replace(hour=23, minute=59, second=59)

            pos = PurchaseOrder.search([
                ('state', 'in', ['purchase', 'done']),
                ('company_id', '=', plan.company_id.id),
                '|',
                '&', ('payment_date', '>=', plan.date_from),
                     ('payment_date', '<=', plan.date_to),
                '&', ('payment_date', '=', False),
                     '&', ('date_order', '>=', plan_start),
                          ('date_order', '<=', plan_end),
            ])
            if not pos:
                continue

            for po in pos:
                document_model, document_id = po._get_budget_document_identity()
                before = Commitment.search_count([
                    ('document_model', '=', document_model),
                    ('document_id', '=', document_id),
                    ('budget_source', '=', 'monthly'),
                    ('state', 'in', ('reserved', 'used')),
                ])
                po._consume_monthly_analytic_budget()
                after = Commitment.search_count([
                    ('document_model', '=', document_model),
                    ('document_id', '=', document_id),
                    ('budget_source', '=', 'monthly'),
                    ('state', 'in', ('reserved', 'used')),
                ])
                if after > before:
                    synced_count += 1

        return synced_count

    def _sync_existing_rfq_reservations(self):
        """Backfill/update reservation commitments for direct RFQs / draft POs."""
        PurchaseOrder = self.env['purchase.order'].sudo()

        synced_count = 0
        for plan in self:
            if not plan.date_from or not plan.date_to:
                continue

            rfqs = PurchaseOrder.search([
                ('state', 'in', ['draft', 'sent', 'to approve']),
                ('company_id', '=', plan.company_id.id),
            ])
            if not rfqs:
                continue

            for po in rfqs:
                po_date = po.payment_date or (po.date_order.date() if po.date_order else False)
                if not po_date or not (plan.date_from <= po_date <= plan.date_to):
                    continue
                if po._has_active_source_requisition_for_plan(plan):
                    continue
                before = self.env['budget.commitment'].sudo().search_count([
                    ('document_model', '=', po._name),
                    ('document_id', '=', po.id),
                    ('budget_source', '=', 'monthly'),
                    ('state', '=', 'reserved'),
                ])
                po._reserve_monthly_budget_for_direct_rfq()
                after = self.env['budget.commitment'].sudo().search_count([
                    ('document_model', '=', po._name),
                    ('document_id', '=', po.id),
                    ('budget_source', '=', 'monthly'),
                    ('state', '=', 'reserved'),
                ])
                if after > before:
                    synced_count += 1

        return synced_count

    def _sync_existing_bill_reservations(self):
        """Backfill/update reservation commitments for vendor bills."""
        AccountMove = self.env['account.move'].sudo()

        synced_count = 0
        for plan in self:
            if not plan.date_from or not plan.date_to:
                continue

            # Filter at DB level using invoice_date_due to reduce dataset size.
            # Bills without a due date (PO-linked) are included via the OR clause
            # and will be further filtered by _get_bill_target_date() in the loop.
            bills = AccountMove.search([
                ('move_type', 'in', ('in_invoice', 'in_refund')),
                ('state', 'in', ('draft', 'posted')),
                ('company_id', '=', plan.company_id.id),
                '|',
                '&', ('invoice_date_due', '>=', plan.date_from),
                     ('invoice_date_due', '<=', plan.date_to),
                ('invoice_date_due', '=', False),
            ])
            if not bills:
                continue

            for bill in bills:
                bill_date = bill._get_bill_target_date()
                if not bill_date or not (plan.date_from <= bill_date <= plan.date_to):
                    continue
                before = self.env['budget.commitment'].sudo().search_count([
                    ('document_model', '=', bill._name),
                    ('document_id', '=', bill.id),
                    ('budget_source', '=', 'monthly'),
                    ('state', 'in', ('reserved', 'used')),
                ])
                bill._sync_monthly_bill_budget()
                after = self.env['budget.commitment'].sudo().search_count([
                    ('document_model', '=', bill._name),
                    ('document_id', '=', bill.id),
                    ('budget_source', '=', 'monthly'),
                    ('state', 'in', ('reserved', 'used')),
                ])
                if after > before:
                    synced_count += 1

        return synced_count

    def _sync_existing_reservations(self):
        """Backfill/update commitments for documents that predate the active plan."""
        self.ensure_one()
        synced_pr_count = self._sync_existing_pr_reservations()
        synced_po_count = self._sync_existing_po_reservations()
        synced_rfq_count = self._sync_existing_rfq_reservations()
        synced_bill_count = self._sync_existing_bill_reservations()

        if synced_pr_count or synced_po_count or synced_rfq_count or synced_bill_count:
            parts = []
            if synced_pr_count:
                parts.append(_("PR reservations: %s") % synced_pr_count)
            if synced_po_count:
                parts.append(_("PO reservations: %s") % synced_po_count)
            if synced_rfq_count:
                parts.append(_("RFQ reservations: %s") % synced_rfq_count)
            if synced_bill_count:
                parts.append(_("Bill reservations: %s") % synced_bill_count)
            self.message_post(
                body=_("Synced monthly budget commitments (%s).") % ", ".join(parts)
            )

        return synced_pr_count, synced_po_count, synced_rfq_count, synced_bill_count

    # ── ORM ──────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'monthly.budget.plan') or _('New')
        return super().create(vals_list)

    # ── Constraints ──────────────────────────────────────────────

    @api.constrains('month', 'year')
    def _check_dates(self):
        for plan in self:
            try:
                y = int(plan.year) if plan.year else 0
            except (ValueError, TypeError):
                raise ValidationError(_("ปีต้องเป็นตัวเลข 4 หลัก เช่น 2025"))
            if y and y < 2000:
                raise ValidationError(_("ปีต้องเป็น ค.ศ. 2000 หรือหลังจากนั้น"))
            if not plan.month or not y:
                raise ValidationError(_("กรุณาระบุเดือนและปี"))

    @api.constrains('budget_line_ids', 'total_budget')
    def _check_allocation(self):
        for plan in self:
            total_pct = sum(plan.budget_line_ids.mapped('percentage'))
            if total_pct > 100.0001:
                raise ValidationError(
                    _('Total percentage of budget lines (%.2f%%) exceeds 100%%.') % total_pct
                )

    @api.constrains('state', 'budget_line_ids', 'month', 'year', 'company_id')
    def _check_no_analytic_overlap(self):
        """Prevent the same analytic account from being assigned to more than one
        confirmed plan for the same month, year and company.

        Rule: analytic accounts in a month must be unique across all confirmed plans
        (each analytic belongs to exactly ONE plan per month).
        """
        for plan in self:
            if plan.state != 'confirmed':
                continue
            if not plan.month or not plan.year:
                continue

            # Collect analytics configured on THIS plan
            own_analytic_ids = set(plan.budget_line_ids.mapped('analytic_account_id').ids)
            if not own_analytic_ids:
                continue

            # Find other confirmed plans in the same month/year/company
            other_plans = find_active_monthly_plans(
                self.env, plan.date_from, plan.company_id.id
            ).filtered(lambda p: p.id != plan.id)

            for other in other_plans:
                other_analytic_ids = set(other.budget_line_ids.mapped('analytic_account_id').ids)
                overlap = own_analytic_ids & other_analytic_ids
                if overlap:
                    overlap_names = ', '.join(
                        self.env['account.analytic.account']
                        .browse(list(overlap))
                        .mapped('display_name')
                    )
                    raise ValidationError(_(
                        'Analytic account(s) \"%(analytics)s\" are already configured '
                        'in another confirmed plan for the same month (%(other_plan)s).\n'
                        'Each analytic account must belong to only ONE confirmed plan per month.'
                    ) % {
                        'analytics': overlap_names,
                        'other_plan': other.name,
                    })

    # ── State actions ────────────────────────────────────────────

    def action_confirm(self):
        self.ensure_one()
        if self.state != 'draft':
            raise ValidationError(_('Only draft plans can be confirmed.'))
        self.write({'state': 'confirmed'})
        self._sync_existing_reservations()
        # Single snapshot + MV refresh at the end (avoids double refresh from _sync_existing_reservations)
        self._refresh_budget_snapshot(refresh_report=True)

    def action_close(self):
        self.ensure_one()
        if self.state != 'confirmed':
            raise ValidationError(_('Only confirmed plans can be closed.'))
        self.write({'state': 'closed'})
        # Refresh materialized view on plan close
        try:
            self.env['monthly.budget.report'].refresh_materialized_view()
        except Exception as e:
            _logger.warning('Could not refresh budget report MV after plan close: %s', e)

    def action_reset_draft(self):
        self.ensure_one()
        self.write({'state': 'draft'})

    def action_recompute_budget(self):
        """
        Recompute budget by refreshing all live computed fields.

        How it works:
        - It first clears all existing monthly commitments for this plan's period.
        - Then it loops through PRs, POs, RFQs, and Bills to rebuild the true audit trail.
        - Finally, it refreshes the materialized views.
        """
        self.ensure_one()

        # Hard reset: clear all existing monthly commitments for this plan period
        if self.date_from and self.date_to:
            domain = [
                ('budget_source', '=', 'monthly'),
                ('company_id', '=', self.company_id.id),
                ('date', '>=', self.date_from),
                ('date', '<=', self.date_to),
            ]
            old_commitments = self.env['budget.commitment'].sudo().search(domain)
            if old_commitments:
                old_commitments.unlink()

        self._sync_existing_reservations()

        # Refresh the current plan snapshot and dashboard MV in one place.
        self._refresh_budget_snapshot(refresh_report=True)

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def action_backfill_monthly_budget_commitments(self):
        """One-time backfill for legacy documents and commitments."""
        self.ensure_one()
        if self.state != 'confirmed':
            raise ValidationError(_("Only confirmed plans can run backfill."))

        pr_count, po_count, rfq_count, bill_count = self._sync_existing_reservations()
        self._refresh_budget_snapshot(refresh_report=True)

        self.message_post(
            body=_(
                "One-time budget backfill completed. PR: %s, PO: %s, RFQ: %s, Bill: %s"
            ) % (pr_count, po_count, rfq_count, bill_count)
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    # ── Feature 2: Amendment History ─────────────────────────────

    def write(self, vals):
        """Override to auto-track total_budget changes without formal wizard."""
        if 'total_budget' in vals and not self.env.context.get('skip_amendment_tracking'):
            for plan in self:
                old_budget = plan.total_budget
                new_budget = vals['total_budget']
                if old_budget != new_budget:
                    change_amount = new_budget - old_budget
                    amendment_type = 'increase' if change_amount >= 0 else 'decrease'
                    self.env['monthly.budget.amendment'].create({
                        'plan_id': plan.id,
                        'amendment_type': amendment_type,
                        'amount_before': old_budget,
                        'amount_change': change_amount,
                        'amount_after': new_budget,
                        'reason': _('Direct budget adjustment via form'),
                    })
        return super().write(vals)

    def action_amend_budget(self):
        self.ensure_one()
        return {
            'name': _('Amend Total Budget'),
            'type': 'ir.actions.act_window',
            'res_model': 'monthly.budget.amendment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_plan_id': self.id,
                'default_current_budget': self.total_budget,
                'default_new_total_budget': self.total_budget,
            }
        }

    # ── Feature 1: Budget Rollover ───────────────────────────────

    def action_carry_forward(self):
        """
        Carry forward remaining budget to the next month's plan.
        """
        self.ensure_one()
        if self.state not in ('confirmed', 'closed'):
            raise ValidationError(_("Only confirmed or closed plans can be carried forward."))
        if not self.carry_forward:
            raise ValidationError(_("This plan does not have 'Carry Forward Surplus' enabled."))

        # Snapshot current balances BEFORE any recompute that may alter commitments
        self._refresh_budget_snapshot(refresh_report=False)
        carry_snapshot = {line.id: line.available_amount for line in self.budget_line_ids}

        # Find or create next month's plan
        m = int(self.month)
        y = int(self.year)
        next_m = 1 if m == 12 else m + 1
        next_y = y + 1 if m == 12 else y

        next_plan = self.search([
            ('month', '=', str(next_m)),
            ('year', '=', str(next_y)),
            ('company_id', '=', self.company_id.id)
        ], limit=1)

        if not next_plan:
            next_plan = self.create({
                'name': _('New'),
                'month': str(next_m),
                'year': str(next_y),
                'company_id': self.company_id.id,
                'total_budget': 0.0,
                'source_plan_id': self.id,
            })
        elif next_plan.state != 'draft':
            raise ValidationError(_("The next month's plan (%s) is already confirmed. Cannot carry forward.") % next_plan.name)

        if not next_plan.source_plan_id:
            next_plan.source_plan_id = self.id

        # Loop through lines and carry forward
        rollover_total = 0.0
        lines_updated = 0
        BudgetLine = self.env['monthly.budget.line']

        for line in self.budget_line_ids:
            carry_amt = carry_snapshot.get(line.id, 0.0)
            if carry_amt <= 0:
                continue

            # Apply cap if configured
            if self.carry_forward_cap > 0:
                cap_amt = line.budget_amount * (self.carry_forward_cap / 100.0)
                carry_amt = min(carry_amt, cap_amt)
                
            if carry_amt <= 0:
                continue

            # Match dimension in next plan
            dims = {
                'analytic_account_id': line.analytic_account_id.id,
                'department_id': line.department_id.id if line.department_id else False,
                'project_id': line.project_id.id if line.project_id else False,
                'category': line.category,
            }
            # Look for existing line with exact match
            existing_line = BudgetLine.search([
                ('plan_id', '=', next_plan.id),
                ('analytic_account_id', '=', dims['analytic_account_id']),
                ('department_id', '=', dims['department_id']),
                ('project_id', '=', dims['project_id']),
                ('category', '=', dims['category']),
            ], limit=1)

            if existing_line:
                existing_line.carried_amount += carry_amt
            else:
                BudgetLine.create({
                    'plan_id': next_plan.id,
                    'analytic_account_id': dims['analytic_account_id'],
                    'department_id': dims['department_id'],
                    'project_id': dims['project_id'],
                    'category': dims['category'],
                    'carried_amount': carry_amt,
                    'percentage': 0.0,
                })
            
            rollover_total += carry_amt
            lines_updated += 1

        next_plan._refresh_budget_snapshot(refresh_report=True)

        self.message_post(body=_("Carried forward {:,.2f} from {} lines to plan {}.").format(
            rollover_total, lines_updated, next_plan.name
        ))
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'monthly.budget.plan',
            'res_id': next_plan.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ── Feature 3: Auto-close Expired Plans ───────────────────────

    @api.model
    def _cron_auto_close_expired_plans(self):
        """Cron job to close plans whose period has passed."""
        today = fields.Date.today()
        expired_plans = self.search([
            ('state', '=', 'confirmed'),
            ('date_to', '<', today)
        ])
        for plan in expired_plans:
            try:
                plan.action_close()
                plan.message_post(body=_("Plan auto-closed by scheduled cron job (period ended)."))
                _logger.info('Auto-closed expired budget plan: %s', plan.name)
            except Exception as e:
                _logger.error(
                    'Auto-close failed for budget plan %s (%s): %s',
                    plan.name, plan.id, e,
                )

    @api.model
    def _cron_refresh_confirmed_plans(self):
        """Cron job to refresh all confirmed budget plan snapshots.

        Only processes plans that have budget commitments (activity) to avoid
        unnecessary work on empty plans.  Refreshes plan line balances and
        the materialized view in one pass.
        """
        confirmed_plans = self.search([('state', '=', 'confirmed')])
        if not confirmed_plans:
            return

        Commitment = self.env['budget.commitment'].sudo()
        refreshed = 0
        for plan in confirmed_plans:
            if not plan.date_from or not plan.date_to:
                continue
            # Only refresh plans that have at least one commitment in their period
            has_activity = Commitment.search_count([
                ('budget_source', '=', 'monthly'),
                ('company_id', '=', plan.company_id.id),
                ('date', '>=', plan.date_from),
                ('date', '<=', plan.date_to),
                ('state', 'in', ('reserved', 'used')),
            ])
            if not has_activity and not plan.budget_line_ids.filtered(lambda l: l.reserved_amount or l.used_amount):
                continue
            try:
                plan._refresh_budget_snapshot(refresh_report=False)
                refreshed += 1
            except Exception as e:
                _logger.error('Cron refresh failed for plan %s (%s): %s', plan.name, plan.id, e)

        # Single MV refresh at the end (not per-plan)
        try:
            self.env['monthly.budget.report'].refresh_materialized_view()
        except Exception as e:
            _logger.warning('Cron MV refresh failed: %s', e)

        _logger.info('Cron refreshed %d/%d confirmed budget plan snapshots', refreshed, len(confirmed_plans))
