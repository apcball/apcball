# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, tools, _

_logger = logging.getLogger(__name__)


class MonthlyBudgetVariance(models.Model):
    """
    Budget Variance Analysis — read-only SQL view.

    Provides a side-by-side comparison of budgeted vs actual amounts
    for each budget line, including variance (absolute and percentage)
    and a traffic-light status indicator.
    """
    _name = 'monthly.budget.variance'
    _description = 'Monthly Budget Variance Analysis'
    _auto = False
    _order = 'plan_id desc, variance_pct asc'

    plan_id = fields.Many2one(
        'monthly.budget.plan',
        string='Budget Plan',
        readonly=True,
    )
    plan_name = fields.Char(
        string='Plan',
        readonly=True,
    )
    plan_state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
            ('closed', 'Closed'),
        ],
        string='Plan Status',
        readonly=True,
    )
    month = fields.Char(string='Month', readonly=True)
    year = fields.Char(string='Year', readonly=True)
    date_from = fields.Date(string='Period Start', readonly=True)
    date_to = fields.Date(string='Period End', readonly=True)
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account',
        readonly=True,
    )
    department_id = fields.Many2one(
        'hr.department',
        string='Department',
        readonly=True,
    )
    project_id = fields.Many2one(
        'project.project',
        string='Project',
        readonly=True,
    )
    category = fields.Selection(
        selection=[
            ('capex', 'CapEx'),
            ('opex', 'OpEx'),
        ],
        string='Category',
        readonly=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        readonly=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        readonly=True,
    )
    budget_amount = fields.Monetary(
        string='Budget',
        currency_field='currency_id',
        readonly=True,
    )
    carried_amount = fields.Monetary(
        string='Carried Forward',
        currency_field='currency_id',
        readonly=True,
    )
    total_budget = fields.Monetary(
        string='Total Budget',
        currency_field='currency_id',
        readonly=True,
        help='Budget + Carried Forward',
    )
    fixed_cost_amount = fields.Monetary(
        string='Fixed Costs',
        currency_field='currency_id',
        readonly=True,
    )
    reserved_amount = fields.Monetary(
        string='Reserved',
        currency_field='currency_id',
        readonly=True,
    )
    used_amount = fields.Monetary(
        string='Actual Used',
        currency_field='currency_id',
        readonly=True,
    )
    total_committed = fields.Monetary(
        string='Total Committed',
        currency_field='currency_id',
        readonly=True,
        help='Fixed + Reserved + Used',
    )
    available_amount = fields.Monetary(
        string='Available',
        currency_field='currency_id',
        readonly=True,
    )
    variance_amount = fields.Monetary(
        string='Variance',
        currency_field='currency_id',
        readonly=True,
        help='Budget - Used (positive = under budget)',
    )
    variance_pct = fields.Float(
        string='Variance %',
        readonly=True,
        help='(Budget - Used) / Budget * 100',
    )
    utilization_pct = fields.Float(
        string='Utilization %',
        readonly=True,
        help='(Fixed + Reserved + Used) / Budget * 100',
    )
    status = fields.Selection(
        selection=[
            ('ok', '✅ Within Budget'),
            ('warning', '⚠️ Near Limit (>80%)'),
            ('over', '🔴 Over Budget'),
        ],
        string='Status',
        readonly=True,
    )

    def init(self):
        """Create or replace the SQL view."""
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    bl.id AS id,
                    bl.plan_id,
                    p.name AS plan_name,
                    p.state AS plan_state,
                    p.month,
                    p.year,
                    p.date_from,
                    p.date_to,
                    bl.analytic_account_id,
                    bl.department_id,
                    bl.project_id,
                    bl.category,
                    p.company_id,
                    p.currency_id,
                    bl.budget_amount,
                    COALESCE(bl.carried_amount, 0) AS carried_amount,
                    bl.budget_amount + COALESCE(bl.carried_amount, 0) AS total_budget,
                    0.0 AS fixed_cost_amount,
                    0.0 AS reserved_amount,
                    0.0 AS used_amount,
                    0.0 AS total_committed,
                    bl.budget_amount + COALESCE(bl.carried_amount, 0) AS available_amount,
                    bl.budget_amount AS variance_amount,
                    CASE WHEN bl.budget_amount > 0
                         THEN 100.0
                         ELSE 0 END AS variance_pct,
                    0.0 AS utilization_pct,
                    'ok'::text AS status
                FROM monthly_budget_line bl
                JOIN monthly_budget_plan p ON p.id = bl.plan_id
                WHERE p.state IN ('confirmed', 'closed')
            )
        """ % self._table)

    # ── Drill-down API ────────────────────────────────────────────

    def action_view_purchase_orders(self):
        """Open POs that contribute to this line's used/reserved amounts."""
        self.ensure_one()
        plan = self.plan_id
        domain = [
            ('state', 'in', ['purchase', 'done']),
            ('company_id', '=', plan.company_id.id),
        ]
        if plan.date_from and plan.date_to:
            domain += [
                '|',
                '&', ('payment_date', '>=', plan.date_from),
                     ('payment_date', '<=', plan.date_to),
                '&', ('payment_date', '=', False),
                     '&', ('date_order', '>=', fields.Datetime.to_datetime(plan.date_from)),
                          ('date_order', '<=', fields.Datetime.to_datetime(plan.date_to)),
            ]
        return {
            'name': _('Purchase Orders — %s') % self.analytic_account_id.name,
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'view_mode': 'tree,form',
            'domain': domain,
            'context': {'search_default_order_date': 1},
        }

    def action_view_invoices(self):
        """Open vendor bills that contribute to this line's used amount."""
        self.ensure_one()
        plan = self.plan_id
        analytic_str = str(self.analytic_account_id.id)
        # Find invoice lines with this analytic in their distribution
        aml_domain = [
            ('move_id.move_type', 'in', ('in_invoice', 'in_refund')),
            ('move_id.state', '=', 'posted'),
            ('company_id', '=', plan.company_id.id),
            ('date', '>=', plan.date_from),
            ('date', '<=', plan.date_to),
            ('analytic_distribution', '!=', False),
        ]
        amls = self.env['account.move.line'].sudo().search(aml_domain)
        move_ids = set()
        for aml in amls:
            dist = aml.analytic_distribution or {}
            if analytic_str in dist:
                move_ids.add(aml.move_id.id)

        return {
            'name': _('Vendor Bills — %s') % self.analytic_account_id.name,
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', list(move_ids))],
        }

    def action_view_requisitions(self):
        """Open PRs that contribute to this line's reserved amount."""
        self.ensure_one()
        plan = self.plan_id
        domain = [
            ('state', 'not in', ('draft', 'cancel', 'cancelled', 'rejected')),
            ('payment_date', '>=', plan.date_from),
            ('payment_date', '<=', plan.date_to),
            ('company_id', '=', plan.company_id.id),
        ]
        return {
            'name': _('Purchase Requisitions — %s') % self.analytic_account_id.name,
            'type': 'ir.actions.act_window',
            'res_model': 'employee.purchase.requisition',
            'view_mode': 'tree,form',
            'domain': domain,
        }
