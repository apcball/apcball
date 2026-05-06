# -*- coding: utf-8 -*-
import logging
from collections import defaultdict
from odoo import api, fields, models, tools

_logger = logging.getLogger(__name__)


class MonthlyBudgetReport(models.Model):
    _name = 'monthly.budget.report'
    _description = 'Monthly Budget Analysis Report'
    _auto = False
    _order = 'date desc'

    budget_line_id = fields.Many2one('monthly.budget.line', string='Budget Line', readonly=True)
    plan_id = fields.Many2one('monthly.budget.plan', string='Budget Plan', readonly=True)
    analytic_account_id = fields.Many2one('account.analytic.account', string='Analytic Account', readonly=True)
    department_id = fields.Many2one('hr.department', string='Department', readonly=True)
    project_id = fields.Many2one('project.project', string='Project', readonly=True)
    category = fields.Selection([
        ('capex', 'งบลงทุน (CapEx)'),
        ('opex', 'งบดำเนินงาน (OpEx)'),
    ], string='Category', readonly=True)
    entry_type = fields.Selection([
        ('budget', 'Budget Limit'),
        ('reserved', 'Reserved'),
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

    _MV_NAME = 'monthly_budget_report_mv'

    def init(self):
        """
        Create the PostgreSQL Materialized View backing this model.

        On first install, drops any existing regular view and creates a
        materialized view with supporting indexes.  On subsequent upgrades,
        the ``IF NOT EXISTS`` guard is a no-op — we just refresh the data.

        Indexes:
          * UNIQUE on id   → required for CONCURRENTLY refresh
          * idx_mbr_analytic  (analytic_account_id)
          * idx_mbr_date      (date)
          * idx_mbr_plan      (plan_id)
        """
        cr = self.env.cr

        # Drop the old plain view if it exists (idempotent on upgrade)
        cr.execute("DROP VIEW IF EXISTS %s CASCADE" % self._table)
        cr.execute("DROP MATERIALIZED VIEW IF EXISTS %s CASCADE" % self._MV_NAME)

        # Build inner SQL (same logic, just wrapped in the MV DDL)
        inner_sql = """
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
                    wbl.analytic_account_id as analytic_account_id,
                    wbl.department_id as department_id,
                    wbl.project_id as project_id,
                    wbl.category as category
                FROM monthly_budget_line wbl
                JOIN monthly_budget_plan wbp ON wbl.plan_id = wbp.id
                WHERE wbp.state = 'confirmed'

                UNION ALL

                -- Used entries (monthly budget commitments in used state)
                SELECT
                    'actual' as entry_type,
                    COALESCE(bc.document_ref, bc.document_model || ':' || bc.document_id::text) as name,
                    bc.amount as amount,
                    0.0 as budget_amt,
                    bc.amount as actual_amt,
                    -bc.amount as remaining_amt,
                    100.0 as utilization,
                    bc.date as date,
                    bc.company_id as company_id,
                    wbl.id as budget_line_id,
                    wbl.plan_id as plan_id,
                    wbl.analytic_account_id as analytic_account_id,
                    wbl.department_id as department_id,
                    wbl.project_id as project_id,
                    wbl.category as category
                FROM budget_commitment bc
                JOIN monthly_budget_plan wbp ON
                    bc.date >= wbp.date_from AND
                    bc.date <= wbp.date_to AND
                    wbp.company_id = bc.company_id AND
                    wbp.state = 'confirmed'
                JOIN monthly_budget_line wbl ON
                    wbl.plan_id = wbp.id AND
                    wbl.analytic_account_id = bc.analytic_account_id
                WHERE bc.budget_source = 'monthly'
                  AND bc.state = 'used'

                UNION ALL

                -- Reserved: monthly budget commitments in reserved state
                SELECT
                    'reserved' as entry_type,
                    COALESCE(bc.document_ref, bc.document_model || ':' || bc.document_id::text) as name,
                    bc.amount as amount,
                    0.0 as budget_amt,
                    0.0 as actual_amt,
                    -bc.amount as remaining_amt,
                    0.0 as utilization,
                    bc.date as date,
                    bc.company_id as company_id,
                    wbl.id as budget_line_id,
                    wbl.plan_id as plan_id,
                    wbl.analytic_account_id as analytic_account_id,
                    wbl.department_id as department_id,
                    wbl.project_id as project_id,
                    wbl.category as category
                FROM budget_commitment bc
                JOIN monthly_budget_plan wbp ON
                    bc.date >= wbp.date_from AND
                    bc.date <= wbp.date_to AND
                    wbp.company_id = bc.company_id AND
                    wbp.state = 'confirmed'
                JOIN monthly_budget_line wbl ON
                     wbl.plan_id = wbp.id AND
                     wbl.analytic_account_id = bc.analytic_account_id
                WHERE bc.budget_source = 'monthly'
                  AND bc.state = 'reserved'

            )
            SELECT
                row_number() OVER () AS id,
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
                re.analytic_account_id,
                re.department_id,
                re.project_id,
                re.category
            FROM report_entries re
        """

        # Create the materialized view (skipped if already exists)
        cr.execute("""
            CREATE MATERIALIZED VIEW IF NOT EXISTS {mv}
            AS {sql}
            WITH DATA
        """.format(mv=self._MV_NAME, sql=inner_sql))

        # Unique index on id (required for REFRESH CONCURRENTLY)
        cr.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS {mv}_uid
            ON {mv} (id)
        """.format(mv=self._MV_NAME))

        # Query-acceleration indexes
        cr.execute("""
            CREATE INDEX IF NOT EXISTS idx_mbr_analytic
            ON {mv} (analytic_account_id)
        """.format(mv=self._MV_NAME))
        cr.execute("""
            CREATE INDEX IF NOT EXISTS idx_mbr_date
            ON {mv} (date)
        """.format(mv=self._MV_NAME))
        cr.execute("""
            CREATE INDEX IF NOT EXISTS idx_mbr_plan
            ON {mv} (plan_id)
        """.format(mv=self._MV_NAME))

        # Point Odoo's _table to the materialized view so ORM reads work
        cr.execute("""
            CREATE OR REPLACE VIEW {tbl} AS
            SELECT * FROM {mv}
        """.format(tbl=self._table, mv=self._MV_NAME))

        _logger.info('monthly.budget.report: materialized view %s initialised', self._MV_NAME)

    # ── Materialized View Refresh ────────────────────────────────

    @api.model
    def refresh_materialized_view(self):
        """
        Refresh the materialized view concurrently so reads are never blocked.
        Uses psycopg2.sql for safe SQL composition.
        """
        from psycopg2 import sql
        try:
            self.env.cr.execute(
                sql.SQL('REFRESH MATERIALIZED VIEW CONCURRENTLY {}').format(
                    sql.Identifier(self._MV_NAME)
                )
            )
            _logger.info('monthly.budget.report: materialized view %s refreshed (CONCURRENTLY)', self._MV_NAME)
        except Exception as e:
            _logger.warning(
                'monthly.budget.report: CONCURRENTLY refresh failed, falling back to full refresh: %s', e
            )
            try:
                self.env.cr.execute(
                    sql.SQL('REFRESH MATERIALIZED VIEW {}').format(
                        sql.Identifier(self._MV_NAME)
                    )
                )
                _logger.info('monthly.budget.report: materialized view %s refreshed (full)', self._MV_NAME)
            except Exception as e2:
                _logger.error('monthly.budget.report: failed to refresh %s: %s', self._MV_NAME, e2)

    @api.model
    def get_available_years(self):
        """Return list of distinct years from confirmed budget plans."""
        plans = self.env['monthly.budget.plan'].search([('state', '=', 'confirmed')])
        years = sorted(set(p.date_from.year for p in plans if p.date_from), reverse=True)
        return years

    # ── Dashboard Data API (SQL Aggregation) ─────────────────────

    @api.model
    def get_available_plans(self, company_id=None):
        """Return list of confirmed budget plans for the dropdown selector."""
        domain = [('state', '=', 'confirmed')]
        if company_id:
            domain.append(('company_id', '=', int(company_id)))
        plans = self.env['monthly.budget.plan'].search(domain, order='year desc, month desc')
        return [
            {
                'id': p.id,
                'name': p.name,
                'month': p.month,
                'year': p.year,
                'date_from': p.date_from.isoformat() if p.date_from else '',
                'date_to': p.date_to.isoformat() if p.date_to else '',
                'label': '%s/%s — %s' % (p.month.zfill(2), p.year, p.name),
            }
            for p in plans
        ]

    @api.model
    def get_dashboard_data(self, filters=None):
        """Fetch summarized data for the OWL dashboard components using SQL aggregation."""
        # Ensure realtime data by refreshing the materialized view before query
        self.refresh_materialized_view()
        
        if filters is None:
            filters = {}

        # 1. Resolve Plans based on plan_id (direct) or year/month/company
        domain = [('state', '=', 'confirmed')]
        if filters.get('company_id'):
            domain.append(('company_id', '=', int(filters['company_id'])))
        
        # Direct plan_id filter takes priority over year/month
        if filters.get('plan_id'):
            domain.append(('id', '=', int(filters['plan_id'])))
            plans = self.env['monthly.budget.plan'].search(domain)
        else:
            plans = self.env['monthly.budget.plan'].search(domain)
            year = filters.get('year')
            month = filters.get('month')
            if year:
                plans = plans.filtered(lambda p: p.date_from and p.date_from.year == int(year))
            if month:
                plans = plans.filtered(lambda p: p.date_from and p.date_from.month == int(month))

        plan_ids = plans.ids
        if not plan_ids:
            return {
                'kpi': self._get_kpi([]),
                'waterfall': self._get_waterfall([]),
                'analytic_breakdown': [],
                'stacked_bar': [],
                'trend': [],
                'alerts': [],
            }

        # 2. Get Analytic Breakdown (Core Data)
        breakdown_data = self._get_analytic_breakdown(plan_ids, filters)

        return {
            'kpi': self._get_kpi(breakdown_data),
            'waterfall': self._get_waterfall(breakdown_data),
            'analytic_breakdown': breakdown_data,
            'stacked_bar': self._get_stacked_bar(breakdown_data),
            'trend': self._get_trend(plan_ids, filters),
            'alerts': self._get_alerts(breakdown_data),
        }


    def _get_analytic_breakdown(self, plan_ids, filters):
        """Execute raw SQL to get multi-dimension aggregation."""
        query_filters = []
        params = [tuple(plan_ids)]
        
        if filters.get('department_id'):
            query_filters.append("AND mbr.department_id = %s")
            params.append(int(filters['department_id']))
        if filters.get('project_id'):
            query_filters.append("AND mbr.project_id = %s")
            params.append(int(filters['project_id']))
        if filters.get('category'):
            query_filters.append("AND mbr.category = %s")
            params.append(filters['category'])

        filter_clause = " ".join(query_filters)

        query = f"""
            SELECT
                mbr.analytic_account_id,
                mbr.department_id,
                mbr.project_id,
                mbr.category,
                SUM(CASE WHEN mbr.entry_type = 'budget' THEN mbr.budget_amt ELSE 0 END) AS budget,
                SUM(CASE WHEN mbr.entry_type = 'reserved' THEN mbr.amount ELSE 0 END) AS reserved,
                SUM(CASE WHEN mbr.entry_type = 'actual' THEN mbr.actual_amt ELSE 0 END) AS used
            FROM monthly_budget_report mbr
            WHERE mbr.plan_id IN %s {filter_clause}
            GROUP BY mbr.analytic_account_id, mbr.department_id, mbr.project_id, mbr.category
        """

        self.env.cr.execute(query, params)
        rows = self.env.cr.dictfetchall()

        # Fetch names using ORM to properly support translated (jsonb) fields
        analytic_ids = list(set(r['analytic_account_id'] for r in rows if r['analytic_account_id']))
        dept_ids = list(set(r['department_id'] for r in rows if r['department_id']))
        proj_ids = list(set(r['project_id'] for r in rows if r['project_id']))

        analytics = {a.id: a.display_name for a in self.env['account.analytic.account'].browse(analytic_ids)}
        depts = {d.id: d.display_name for d in self.env['hr.department'].browse(dept_ids)}
        projs = {p.id: p.display_name for p in self.env['project.project'].browse(proj_ids)}

        result = []
        for r in rows:
            budget = r['budget'] or 0.0
            reserved = r['reserved'] or 0.0
            used = r['used'] or 0.0
            
            available = budget - reserved - used
            utilization = (reserved + used) / budget if budget else 0.0

            result.append({
                'analytic': analytics.get(r['analytic_account_id'], 'General'),
                'department': depts.get(r['department_id'], '-'),
                'project': projs.get(r['project_id'], '-'),
                'category': r['category'] or '-',
                'budget': budget,
                'reserved': reserved,
                'used': used,
                'available': available,
                'utilization': utilization,
            })

        return result

    def _get_stacked_bar(self, breakdown_data):
        """Format data for stacked bar chart."""
        return [
            {
                'label': f"{d['analytic']} {d['department'] if d['department'] != '-' else ''}".strip(),
                'budget': d['budget'],
                'reserved': d['reserved'],
                'used': d['used'],
            }
            for d in breakdown_data
            if d['budget'] > 0 or d['reserved'] > 0 or d['used'] > 0
        ]

    def _get_kpi(self, breakdown_data):
        total_budget = sum(d['budget'] for d in breakdown_data)
        total_reserved = sum(d['reserved'] for d in breakdown_data)
        total_used = sum(d['used'] for d in breakdown_data)
        total_available = total_budget - total_reserved - total_used
        utilization = (total_reserved + total_used) / total_budget * 100 if total_budget else 0.0
        burn_rate = total_used / total_budget if total_budget else 0.0

        return {
            'total_budget': total_budget,
            'reserved': total_reserved,
            'used': total_used,
            'available': max(0.0, total_available),
            'utilization': utilization,
            'burn_rate': burn_rate,
        }

    def _get_waterfall(self, breakdown_data):
        kpi = self._get_kpi(breakdown_data)
        return [
            {'label': 'Total Budget', 'value': kpi['total_budget']},
            {'label': 'Reserved', 'value': -kpi['reserved']},
            {'label': 'Used', 'value': -kpi['used']},
            {'label': 'Remaining', 'value': kpi['available']},
        ]

    def _get_trend(self, plan_ids, filters):
        """Get trend by month by executing SQL on the report model."""
        params = [tuple(plan_ids)]
        query_filters = []
        if filters.get('department_id'):
            query_filters.append("AND department_id = %s")
            params.append(int(filters['department_id']))
        if filters.get('project_id'):
            query_filters.append("AND project_id = %s")
            params.append(int(filters['project_id']))
        if filters.get('category'):
            query_filters.append("AND category = %s")
            params.append(filters['category'])

        filter_clause = " ".join(query_filters)
        
        query = f"""
            SELECT 
                TO_CHAR(date, 'YYYY-MM') as sort_key,
                TO_CHAR(date, 'Mon YYYY') as month_label,
                SUM(CASE WHEN entry_type='budget' THEN budget_amt ELSE 0 END) as budget,
                SUM(CASE WHEN entry_type='actual' THEN actual_amt ELSE 0 END) as used
            FROM monthly_budget_report
            WHERE plan_id IN %s {filter_clause} AND date IS NOT NULL
            GROUP BY TO_CHAR(date, 'YYYY-MM'), TO_CHAR(date, 'Mon YYYY')
            ORDER BY sort_key
        """
        self.env.cr.execute(query, params)
        rows = self.env.cr.dictfetchall()
        
        return [
            {
                'month': r['month_label'],
                'budget': r['budget'] or 0.0,
                'used': r['used'] or 0.0,
            }
            for r in rows
        ]

    def _get_alerts(self, breakdown_data):
        alerts = []
        for line in breakdown_data:
            if line['utilization'] > 0.8:
                alerts.append({
                    'type': 'warning',
                    'message': f"{line['analytic']} ({line['department']}) utilization > 80%"
                })
            
            if line['available'] < 0:
                alerts.append({
                    'type': 'error',
                    'message': f"{line['analytic']} ({line['department']}) over budget!"
                })
        return alerts
