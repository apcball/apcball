# -*- coding: utf-8 -*-
import logging
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class WeeklyBudgetPlan(models.Model):
    _name = 'weekly.budget.plan'
    _description = 'Weekly Budget Plan'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name desc'

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
    )
    year = fields.Char(
        string='Year',
        compute='_compute_year',
        store=True,
    )
    date_from = fields.Date(
        string='Date From',
        required=True,
        tracking=True,
    )
    date_to = fields.Date(
        string='Date To',
        required=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        help='Leave empty for All Companies scope',
        tracking=True,
    )
    all_companies = fields.Boolean(
        string='All Companies',
        default=False,
        tracking=True,
        help='If checked, budget applies to all companies',
    )
    default_weekly_amount = fields.Float(
        string='Default Weekly Amount',
        required=True,
        tracking=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
        required=True,
    )
    notify_user_ids = fields.Many2many(
        'res.users',
        'weekly_budget_plan_notify_user_rel',
        'plan_id',
        'user_id',
        string='Notify Users',
        help='Users to notify when budget is exceeded',
    )
    line_ids = fields.One2many(
        'weekly.budget.line',
        'plan_id',
        string='Weekly Budget Lines',
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True, copy=False)

    # Summary fields
    total_budget = fields.Float(
        string='Total Budget',
        compute='_compute_totals',
        store=True,
    )
    total_used = fields.Float(
        string='Total Used',
        compute='_compute_totals',
        store=True,
    )
    total_remaining = fields.Float(
        string='Total Remaining',
        compute='_compute_totals',
        store=True,
    )
    usage_percentage = fields.Float(
        string='Usage %',
        compute='_compute_totals',
        store=True,
    )

    @api.depends('date_from')
    def _compute_year(self):
        for rec in self:
            rec.year = str(rec.date_from.year) if rec.date_from else ''

    @api.depends('line_ids.amount_limit', 'line_ids.amount_used')
    def _compute_totals(self):
        for rec in self:
            rec.total_budget = sum(rec.line_ids.mapped('amount_limit'))
            rec.total_used = sum(rec.line_ids.mapped('amount_used'))
            rec.total_remaining = rec.total_budget - rec.total_used
            rec.usage_percentage = (
                (rec.total_used / rec.total_budget * 100)
                if rec.total_budget else 0.0
            )

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_from and rec.date_to and rec.date_from > rec.date_to:
                raise ValidationError(_('Date From must be before Date To.'))

    @api.constrains('all_companies', 'company_id')
    def _check_company_scope(self):
        for rec in self:
            if not rec.all_companies and not rec.company_id:
                raise ValidationError(
                    _('Please select a Company or check "All Companies".')
                )

    @api.onchange('all_companies')
    def _onchange_all_companies(self):
        if self.all_companies:
            self.company_id = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'weekly.budget.plan'
                ) or _('New')
        return super().create(vals_list)

    def action_generate_weeks(self):
        """Generate weekly budget lines from date_from to date_to (Mon-Sun)."""
        for rec in self:
            if not rec.date_from or not rec.date_to:
                raise UserError(_('Please set Date From and Date To first.'))

            # Remove existing draft lines
            rec.line_ids.filtered(lambda l: l.amount_used == 0).unlink()

            # Find the Monday on or before date_from
            start = rec.date_from
            # weekday(): Monday=0, Sunday=6
            monday = start - timedelta(days=start.weekday())

            week_num = 1
            while monday <= rec.date_to:
                sunday = monday + timedelta(days=6)
                week_label = 'W%d (%s - %s)' % (
                    week_num,
                    monday.strftime('%d/%m'),
                    sunday.strftime('%d/%m'),
                )

                # Check if line already exists for this week
                existing = rec.line_ids.filtered(
                    lambda l, m=monday, s=sunday: l.date_from == m and l.date_to == s
                )
                if not existing:
                    self.env['weekly.budget.line'].create({
                        'plan_id': rec.id,
                        'name': week_label,
                        'week_number': week_num,
                        'date_from': monday,
                        'date_to': sunday,
                        'amount_limit': rec.default_weekly_amount,
                    })

                week_num += 1
                monday += timedelta(days=7)

    def action_confirm(self):
        for rec in self:
            if not rec.line_ids:
                raise UserError(
                    _('Please generate weekly budget lines before confirming.')
                )
            rec.state = 'confirmed'

    def action_done(self):
        self.write({'state': 'done'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset_draft(self):
        self.write({'state': 'draft'})

    def action_recompute_used(self):
        """Recompute used and reserved amounts for all budget lines."""
        for rec in self:
            rec.line_ids._compute_amount_used()
            rec.line_ids._compute_amount_reserved()
            rec.line_ids._compute_remaining()
