# -*- coding: utf-8 -*-
from odoo import api, fields, models, tools


class MonthlyBudgetReport(models.Model):
    _name = 'monthly.budget.report'
    _description = 'Monthly Budget Analysis Report'
    _auto = False
    _order = 'date desc'

    budget_line_id = fields.Many2one('monthly.budget.line', string='Budget Line', readonly=True)
    plan_id = fields.Many2one('monthly.budget.plan', string='Budget Plan', readonly=True)
    analytic_account_id = fields.Many2one('account.analytic.account', string='Analytic Account', readonly=True)
    entry_type = fields.Selection([
        ('budget', 'Budget Limit'),
        ('actual', 'Actual Spending'),
    ], string='Entry Type', readonly=True)
    name = fields.Char(string='Reference', readonly=True)
    amount = fields.Float(string='Amount', readonly=True)
    date = fields.Date(string='Date', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    
    # Dashboard metrics
    budget_amt = fields.Float(string='Budget Amount', readonly=True)
    actual_amt = fields.Float(string='Actual Amount', readonly=True)
    remaining_amt = fields.Float(string='Remaining', readonly=True)
    utilization = fields.Float(string='Utilization %', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                WITH report_entries AS (
                    -- Budget entries
                    SELECT 
                        'budget' as entry_type,
                        wbl.id::text as name,
                        wbl.budget_amount as amount,
                        wbl.budget_amount as budget_amt,
                        0.0 as actual_amt,
                        wbl.budget_amount as remaining_amt,
                        0.0 as utilization,
                        wbp.date_from as date,
                        wbl.company_id as company_id,
                        wbl.id as budget_line_id,
                        wbl.plan_id as plan_id,
                        wbl.analytic_account_id as analytic_account_id
                    FROM monthly_budget_line wbl
                    JOIN monthly_budget_plan wbp ON wbl.plan_id = wbp.id
                    WHERE wbp.state = 'confirmed'

                    UNION ALL

                    -- Actual entries
                    SELECT 
                        'actual' as entry_type,
                        am.name as name,
                        (CASE WHEN am.move_type = 'in_refund' THEN -aml.price_subtotal ELSE aml.price_subtotal END) * CAST(aml.analytic_distribution->>wbl.analytic_account_id::text AS numeric) / 100.0 as amount,
                        0.0 as budget_amt,
                        (CASE WHEN am.move_type = 'in_refund' THEN -aml.price_subtotal ELSE aml.price_subtotal END) * CAST(aml.analytic_distribution->>wbl.analytic_account_id::text AS numeric) / 100.0 as actual_amt,
                        -((CASE WHEN am.move_type = 'in_refund' THEN -aml.price_subtotal ELSE aml.price_subtotal END) * CAST(aml.analytic_distribution->>wbl.analytic_account_id::text AS numeric) / 100.0) as remaining_amt,
                        100.0 as utilization,
                        aml.date as date,
                        am.company_id as company_id,
                        wbl.id as budget_line_id,
                        wbl.plan_id as plan_id,
                        wbl.analytic_account_id as analytic_account_id
                    FROM account_move_line aml
                    JOIN account_move am ON aml.move_id = am.id
                    JOIN monthly_budget_plan wbp ON 
                        aml.date >= wbp.date_from AND 
                        aml.date <= wbp.date_to AND 
                        wbp.company_id = am.company_id AND
                        wbp.state = 'confirmed'
                    JOIN monthly_budget_line wbl ON 
                         wbl.plan_id = wbp.id
                    WHERE am.state = 'posted'
                      AND am.move_type IN ('in_invoice', 'in_refund')
                      AND aml.analytic_distribution IS NOT NULL
                      AND jsonb_typeof(aml.analytic_distribution) = 'object'
                      AND aml.analytic_distribution ? wbl.analytic_account_id::text
                )
                SELECT
                    row_number() OVER () as id,
                    re.entry_type,
                    re.name,
                    re.amount,
                    re.budget_amt,
                    re.actual_amt,
                    re.remaining_amt,
                    re.utilization,
                    re.date,
                    re.company_id,
                    re.budget_line_id,
                    re.plan_id,
                    re.analytic_account_id
                FROM report_entries re
            )
        """ % self._table)

    @api.model
    def get_available_years(self):
        """Return list of distinct years from confirmed budget plans."""
        plans = self.env['monthly.budget.plan'].search([('state', '=', 'confirmed')])
        years = sorted(set(p.date_from.year for p in plans if p.date_from), reverse=True)
        return years

    @api.model
    def get_dashboard_data(self, domain=[], year=None):
        """Fetch summarized data for the OWL dashboard component."""
        data = self.search_read(domain)

        # Apply year filter at Python level
        if year:
            plan_ids = self.env['monthly.budget.plan'].search([
                ('state', '=', 'confirmed'),
            ]).filtered(lambda p: p.date_from and p.date_from.year == int(year)).ids
            data = [d for d in data if d.get('plan_id') and d['plan_id'][0] in plan_ids]

        # Summary calculations
        total_budget = sum(d['budget_amt'] for d in data)
        total_actual = sum(d['actual_amt'] for d in data)
        remaining = total_budget - total_actual
        utilization = (total_actual / total_budget * 100) if total_budget else 0.0

        # Get reserved amounts from budget lines — force LIVE recompute first
        budget_line_ids = [
            d['budget_line_id'][0] for d in data
            if d.get('budget_line_id')
        ]
        budget_lines = self.env['monthly.budget.line'].sudo().browse(
            list(set(budget_line_ids))
        )
        reserved_by_line = {bl.id: bl.reserved_amount for bl in budget_lines}
        total_reserved = sum(reserved_by_line.values())

        # Grouping by analytic account for bar chart
        analytics = {}
        for d in data:
            analytic_id = d['analytic_account_id'][0] if d['analytic_account_id'] else 'Other'
            analytic_name = d['analytic_account_id'][1] if d['analytic_account_id'] else 'Other'
            if analytic_id not in analytics:
                # find total reserved for this analytic across lines in data
                # Since budget line maps 1:1 to analytic for a plan, and many plans can have the analytic
                # we just aggregate by budget line belonging to this analytic.
                analytic_reserved = sum(
                    reserved_by_line.get(dd['budget_line_id'][0], 0.0) 
                    for dd in data if dd['analytic_account_id'] and dd['analytic_account_id'][0] == analytic_id and dd['entry_type'] == 'budget'
                )
                
                analytics[analytic_id] = {
                    'name': analytic_name,
                    'budget': 0.0,
                    'actual': 0.0,
                    'reserved': analytic_reserved,
                }
            analytics[analytic_id]['budget'] += d['budget_amt']
            analytics[analytic_id]['actual'] += d['actual_amt']

        # Pie chart: Used / Reserved / Available
        available = max(total_budget - total_actual - total_reserved, 0.0)
        pie_data = {
            'labels': ['Actual Used', 'Reserved', 'Available Budget'],
            'values': [
                round(total_actual, 2),
                round(total_reserved, 2),
                round(available, 2),
            ],
        }

        return {
            'summary': {
                'total_budget': total_budget,
                'total_actual': total_actual,
                'total_reserved': total_reserved,
                'remaining': remaining,
                'utilization': utilization,
            },
            'analytics': sorted(analytics.values(), key=lambda x: x['name']),
            'pie_data': pie_data,
        }
