# -*- coding: utf-8 -*-
from odoo import api, fields, models, tools


class WeeklyBudgetReport(models.Model):
    _name = 'weekly.budget.report'
    _description = 'Weekly Budget Analysis Report'
    _auto = False
    _order = 'date desc'

    budget_line_id = fields.Many2one('weekly.budget.line', string='Budget Week', readonly=True)
    plan_id = fields.Many2one('weekly.budget.plan', string='Budget Plan', readonly=True)
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
                        wbl.name as name,
                        wbl.amount_limit as amount,
                        wbl.amount_limit as budget_amt,
                        0.0 as actual_amt,
                        wbl.amount_limit as remaining_amt,
                        0.0 as utilization,
                        wbl.date_from as date,
                        wbl.company_id as company_id,
                        wbl.id as budget_line_id,
                        wbl.plan_id as plan_id
                    FROM weekly_budget_line wbl
                    JOIN weekly_budget_plan wbp ON wbl.plan_id = wbp.id
                    WHERE wbp.state = 'confirmed'

                    UNION ALL

                    -- Actual entries (Based on Vendor Bill Due Date)
                    SELECT 
                        'actual' as entry_type,
                        am.name as name,
                        am.amount_total as amount,
                        0.0 as budget_amt,
                        am.amount_total as actual_amt,
                        -am.amount_total as remaining_amt,
                        100.0 as utilization,
                        am.invoice_date_due as date,
                        am.company_id as company_id,
                        wbl.id as budget_line_id,
                        wbl.plan_id as plan_id
                    FROM account_move am
                    JOIN weekly_budget_line wbl ON 
                        am.invoice_date_due >= wbl.date_from AND 
                        am.invoice_date_due <= wbl.date_to
                    JOIN weekly_budget_plan wbp ON wbl.plan_id = wbp.id
                    WHERE am.move_type = 'in_invoice' AND am.state = 'posted'
                      AND (wbp.all_companies = TRUE OR wbp.company_id = am.company_id)
                      AND wbp.state = 'confirmed'
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
                    re.plan_id
                FROM report_entries re
            )
        """ % self._table)

    @api.model
    def get_available_years(self):
        """Return list of distinct years from confirmed budget plans."""
        plans = self.env['weekly.budget.plan'].search([('state', '=', 'confirmed')])
        years = sorted(set(p.year for p in plans if p.year), reverse=True)
        return years

    @api.model
    def get_dashboard_data(self, domain=[], year=None, month=None):
        """Fetch summarized data for the OWL dashboard component."""
        data = self.search_read(domain)

        # Apply year filter at Python level (filter by plan's year)
        if year:
            plan_ids = self.env['weekly.budget.plan'].search([
                ('state', '=', 'confirmed'),
                ('year', '=', str(year)),
            ]).ids
            data = [d for d in data if d.get('plan_id') and d['plan_id'][0] in plan_ids]

        if month:
            # Filter by the exact date falling within the target month.
            try:
                month_int = int(month)
                filtered_data = []
                for d in data:
                    if d.get('date'):
                        date_val = fields.Date.to_date(d['date'])
                        if date_val and date_val.month == month_int:
                            filtered_data.append(d)
                data = filtered_data
            except (ValueError, TypeError):
                pass

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
        budget_lines = self.env['weekly.budget.line'].sudo().browse(
            list(set(budget_line_ids))
        )
        # Force live recompute so dashboard always shows current reserved value
        if budget_lines:
            budget_lines._compute_amount_reserved()
            budget_lines._compute_remaining()

        reserved_by_line = {bl.id: bl.amount_reserved for bl in budget_lines}
        total_reserved = sum(reserved_by_line.values())

        # Weekly grouping for bar chart
        weeks = {}
        for d in data:
            week_id = d['budget_line_id'][0] if d['budget_line_id'] else 'Other'
            week_name = d['budget_line_id'][1] if d['budget_line_id'] else 'Other'
            if week_id not in weeks:
                weeks[week_id] = {
                    'name': week_name,
                    'budget': 0.0,
                    'actual': 0.0,
                    'reserved': reserved_by_line.get(week_id, 0.0),
                }
            weeks[week_id]['budget'] += d['budget_amt']
            weeks[week_id]['actual'] += d['actual_amt']

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
            'weeks': sorted(weeks.values(), key=lambda x: x['name']),
            'pie_data': pie_data,
        }
