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
    fixed_cost_ids = fields.One2many(
        'monthly.budget.fixed.cost',
        'plan_id',
        string='Fixed Costs',
        copy=True,
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
    fixed_cost_amount = fields.Monetary(
        string='Total Fixed Cost',
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

    @api.depends('month', 'year')
    def _compute_period_dates(self):
        import calendar
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
        'budget_line_ids.reserved_amount',
        'budget_line_ids.used_amount',
        'fixed_cost_ids.amount',
        'fixed_cost_ids.state',
        'total_budget',
    )
    def _compute_totals(self):
        for plan in self:
            lines = plan.budget_line_ids
            plan.allocated_amount = sum(lines.mapped('budget_amount'))
            plan.reserved_amount = sum(lines.mapped('reserved_amount'))
            plan.used_amount = sum(lines.mapped('used_amount'))
            
            confirmed_fixed_costs = plan.fixed_cost_ids.filtered(lambda fc: fc.state == 'confirmed')
            plan.fixed_cost_amount = sum(confirmed_fixed_costs.mapped('amount'))

            plan.available_amount = (
                plan.total_budget - plan.reserved_amount - plan.used_amount - plan.fixed_cost_amount
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
        Recompute reserved and used amounts from scratch.

        Uses the single-source-of-truth `_recompute_line_balance()` on budget
        lines, which re-evaluates the live computed fields instead of trusting
        stored values.  After recomputing, refreshes the materialized view.
        """
        self.ensure_one()

        # Clear commitment audit records for this period / company
        self.env['budget.commitment'].sudo().search([
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('company_id', '=', self.company_id.id),
            ('budget_source', '=', 'monthly')
        ]).unlink()

        # Re-scan Employee Purchase Requisitions
        prs = self.env['employee.purchase.requisition'].sudo().search([
            ('payment_date', '>=', self.date_from),
            ('payment_date', '<=', self.date_to),
            ('state', 'not in', ('draft', 'cancelled')),
            ('company_id', '=', self.company_id.id),
        ])
        for pr in prs:
            pr._reserve_monthly_analytic_budget()

        # Re-scan Purchase Orders (consume reservations)
        pos = self.env['purchase.order'].sudo().search([
            ('payment_date', '>=', self.date_from),
            ('payment_date', '<=', self.date_to),
            ('state', 'in', ('purchase', 'done')),
            ('company_id', '=', self.company_id.id),
        ])
        for po in pos:
            po._consume_monthly_analytic_budget()

        # Recompute line balances from live source-of-truth
        self.budget_line_ids._recompute_line_balance()

        # Refresh the materialized view
        try:
            self.env['monthly.budget.report'].refresh_materialized_view()
        except Exception as e:
            _logger.warning(
                'Could not refresh budget report MV after plan recompute: %s', e
            )

        return True
