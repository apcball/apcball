# -*- coding: utf-8 -*-
import calendar
import logging
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

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

    allocated_amount = fields.Monetary(
        string='Total Allocated',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    reserved_amount = fields.Monetary(
        string='Total Reserved',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    used_amount = fields.Monetary(
        string='Total Used',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    available_amount = fields.Monetary(
        string='Total Available',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    allocated_percentage = fields.Float(
        string='Allocated (%)',
        compute='_compute_totals',
        store=True,
    )
    carried_amount = fields.Monetary(
        string='Total Carried Forward',
        compute='_compute_totals',
        store=True,
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

    # ── State actions ────────────────────────────────────────────

    def action_confirm(self):
        self.ensure_one()
        if self.state != 'draft':
            raise ValidationError(_('Only draft plans can be confirmed.'))
        self.write({'state': 'confirmed'})
        # Refresh materialized view so dashboard shows updated data immediately
        try:
            self.env['monthly.budget.report'].refresh_materialized_view()
        except Exception as e:
            _logger.warning('Could not refresh budget report MV after plan confirm: %s', e)

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
        - reserved_amount, used_amount are all live
          computed fields that read directly from PRs, POs, and Invoices.
        - We simply invalidate the cache so next access recomputes them.
        - The materialized view is refreshed for dashboard accuracy.

        Note: We do NOT re-create commitment audit records here.
        Those are created during the normal PR/PO workflow and serve as
        an audit trail only — they are not the source of truth for amounts.
        """
        self.ensure_one()

        # Invalidate and recompute all budget line balances
        self.budget_line_ids._recompute_line_balance()

        # Recompute plan-level totals
        self.invalidate_recordset([
            'allocated_amount', 'reserved_amount', 'used_amount',
            'available_amount', 'allocated_percentage',
        ])

        # Refresh the materialized view for dashboard
        try:
            self.env['monthly.budget.report'].refresh_materialized_view()
        except Exception as e:
            _logger.warning(
                'Could not refresh budget report MV after plan recompute: %s', e
            )

        return True

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

        # Recompute totals just to be safe before rollover
        self.action_recompute_budget()

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
            if line.available_amount <= 0:
                continue
                
            carry_amt = line.available_amount
            # Apply limit if any
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
            plan.action_close()
            plan.message_post(body=_("Plan auto-closed by scheduled cron job (period ended)."))
            _logger.info('Auto-closed expired budget plan: %s', plan.name)

