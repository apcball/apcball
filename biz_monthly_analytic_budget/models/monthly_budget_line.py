# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class MonthlyBudgetLine(models.Model):
    """
    Line item inside a Monthly Budget Plan.
    Each line belongs to one analytic account and carries a percentage
    of the plan's total budget.
    """
    _name = 'monthly.budget.line'
    _description = 'Monthly Budget Line'
    _order = 'plan_id, analytic_account_id'

    plan_id = fields.Many2one(
        'monthly.budget.plan',
        string='Budget Plan',
        required=True,
        ondelete='cascade',
        index=True,
    )
    company_id = fields.Many2one(
        related='plan_id.company_id',
        store=True,
        index=True,
    )
    currency_id = fields.Many2one(
        related='plan_id.currency_id',
        readonly=True,
        store=True,
    )
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account',
        required=True,
        index=True,
    )
    percentage = fields.Float(
        string='Percentage (%)',
        digits=(5, 2),
        default=0.0,
        help='Percentage of the plan total budget allocated to this analytic account.',
    )
    budget_amount = fields.Monetary(
        string='Budget Amount',
        currency_field='currency_id',
        compute='_compute_budget_amount',
        store=True,
    )
    reserved_amount = fields.Monetary(
        string='Reserved',
        currency_field='currency_id',
        default=0.0,
        readonly=True,
    )
    used_amount = fields.Monetary(
        string='Used',
        currency_field='currency_id',
        default=0.0,
        readonly=True,
    )
    available_amount = fields.Monetary(
        string='Available',
        currency_field='currency_id',
        compute='_compute_available_amount',
        store=True,
    )
    utilization_rate = fields.Float(
        string='Utilization (%)',
        compute='_compute_available_amount',
        store=True,
        help='(Reserved + Used) / Budget Amount * 100',
    )

    # ── Computed ─────────────────────────────────────────────────

    @api.depends('plan_id.total_budget', 'percentage')
    def _compute_budget_amount(self):
        for line in self:
            line.budget_amount = line.plan_id.total_budget * line.percentage / 100.0

    @api.depends('budget_amount', 'reserved_amount', 'used_amount')
    def _compute_available_amount(self):
        for line in self:
            line.available_amount = line.budget_amount - line.reserved_amount - line.used_amount
            if line.budget_amount:
                line.utilization_rate = (
                    (line.reserved_amount + line.used_amount) / line.budget_amount
                )
            else:
                line.utilization_rate = 0.0

    # ── Constraints ──────────────────────────────────────────────

    _sql_constraints = [
        (
            'unique_analytic_per_plan',
            'UNIQUE(plan_id, analytic_account_id)',
            'An analytic account can only appear once per budget plan.',
        ),
    ]

    @api.constrains('percentage')
    def _check_percentage(self):
        for line in self:
            if line.percentage < 0 or line.percentage > 100:
                raise ValidationError(_('Percentage must be between 0 and 100.'))

    # ── Budget update helpers (called from purchase models) ──────

    def _add_reservation(self, amount):
        """Increase reserved amount for this line."""
        self.ensure_one()
        self.reserved_amount += amount

    def _release_reservation(self, amount):
        """Decrease reserved amount (on cancellation)."""
        self.ensure_one()
        new_reserved = max(0.0, self.reserved_amount - amount)
        self.reserved_amount = new_reserved

    def _consume_reservation(self, amount):
        """Move amount from reserved → used."""
        self.ensure_one()
        Released = min(amount, self.reserved_amount)
        self.reserved_amount = max(0.0, self.reserved_amount - Released)
        self.used_amount += amount
