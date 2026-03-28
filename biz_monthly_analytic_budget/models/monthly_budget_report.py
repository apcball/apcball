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
        ('fixed', 'Fixed Cost'),
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

                -- Actual entries (posted vendor bills / credit notes)
                SELECT
                    'actual' as entry_type,
                    am.name as name,
                    (CASE WHEN am.move_type = 'in_refund'
                          THEN -aml.price_subtotal
                          ELSE  aml.price_subtotal END)
                    * CAST(aml.analytic_distribution->>wbl.analytic_account_id::text AS numeric)
                    / 100.0 as amount,
                    0.0 as budget_amt,
                    (CASE WHEN am.move_type = 'in_refund'
                          THEN -aml.price_subtotal
                          ELSE  aml.price_subtotal END)
                    * CAST(aml.analytic_distribution->>wbl.analytic_account_id::text AS numeric)
                    / 100.0 as actual_amt,
                    -((CASE WHEN am.move_type = 'in_refund'
                            THEN -aml.price_subtotal
                            ELSE  aml.price_subtotal END)
                      * CAST(aml.analytic_distribution->>wbl.analytic_account_id::text AS numeric)
                      / 100.0) as remaining_amt,
                    100.0 as utilization,
                    aml.date as date,
                    am.company_id as company_id,
                    wbl.id as budget_line_id,
                    wbl.plan_id as plan_id,
                    wbl.analytic_account_id as analytic_account_id,
                    wbl.department_id as department_id,
                    wbl.project_id as project_id,
                    wbl.category as category
                FROM account_move_line aml
                JOIN account_move am ON aml.move_id = am.id
                JOIN monthly_budget_plan wbp ON
                    aml.date >= wbp.date_from AND
                    aml.date <= wbp.date_to AND
                    wbp.company_id = am.company_id AND
                    wbp.state = 'confirmed'
                JOIN monthly_budget_line wbl ON wbl.plan_id = wbp.id
                WHERE am.state = 'posted'
                  AND am.move_type IN ('in_invoice', 'in_refund')
                  AND aml.analytic_distribution IS NOT NULL
                  AND jsonb_typeof(aml.analytic_distribution) = 'object'
                  AND aml.analytic_distribution ? wbl.analytic_account_id::text

                UNION ALL

                -- Reserved: Active PRs (not yet converted to a confirmed PO)
                SELECT
                    'reserved' as entry_type,
                    pr.name as name,
                    ((prl.quantity * prl.unit_price)
                     * CAST(dist.value AS numeric) / 100.0) as amount,
                    0.0 as budget_amt,
                    0.0 as actual_amt,
                    -((prl.quantity * prl.unit_price)
                      * CAST(dist.value AS numeric) / 100.0) as remaining_amt,
                    0.0 as utilization,
                    pr.payment_date as date,
                    pr.company_id as company_id,
                    wbl.id as budget_line_id,
                    wbl.plan_id as plan_id,
                    wbl.analytic_account_id as analytic_account_id,
                    wbl.department_id as department_id,
                    wbl.project_id as project_id,
                    wbl.category as category
                FROM requisition_order prl
                JOIN employee_purchase_requisition pr ON prl.requisition_product_id = pr.id
                CROSS JOIN jsonb_each_text(prl.analytic_distribution) AS dist(key, value)
                JOIN monthly_budget_plan wbp ON
                    pr.payment_date >= wbp.date_from AND
                    pr.payment_date <= wbp.date_to AND
                    wbp.company_id = pr.company_id AND
                    wbp.state = 'confirmed'
                JOIN monthly_budget_line wbl ON
                     wbl.plan_id = wbp.id AND
                     wbl.analytic_account_id::text = dist.key
                WHERE pr.state NOT IN ('draft', 'cancel', 'cancelled', 'rejected')
                  AND prl.analytic_distribution IS NOT NULL
                  AND jsonb_typeof(prl.analytic_distribution) = 'object'
                  AND NOT EXISTS (
                      SELECT 1 FROM purchase_order po
                      WHERE (po.requisition_order = pr.name
                             OR po.pr_number = pr.name
                             OR po.origin = pr.name)
                        AND po.state IN ('purchase', 'done')
                  )

                UNION ALL

                -- Reserved: RFQs (Draft POs) not linked to an active PR
                SELECT
                    'reserved' as entry_type,
                    po.name as name,
                    (pol.price_subtotal * CAST(dist.value AS numeric) / 100.0) as amount,
                    0.0 as budget_amt,
                    0.0 as actual_amt,
                    -(pol.price_subtotal * CAST(dist.value AS numeric) / 100.0) as remaining_amt,
                    0.0 as utilization,
                    po.payment_date as date,
                    po.company_id as company_id,
                    wbl.id as budget_line_id,
                    wbl.plan_id as plan_id,
                    wbl.analytic_account_id as analytic_account_id,
                    wbl.department_id as department_id,
                    wbl.project_id as project_id,
                    wbl.category as category
                FROM purchase_order_line pol
                JOIN purchase_order po ON pol.order_id = po.id
                CROSS JOIN jsonb_each_text(pol.analytic_distribution) AS dist(key, value)
                JOIN monthly_budget_plan wbp ON
                    po.payment_date >= wbp.date_from AND
                    po.payment_date <= wbp.date_to AND
                    wbp.company_id = po.company_id AND
                    wbp.state = 'confirmed'
                JOIN monthly_budget_line wbl ON
                     wbl.plan_id = wbp.id AND
                     wbl.analytic_account_id::text = dist.key
                WHERE po.state = 'draft'
                  AND pol.analytic_distribution IS NOT NULL
                  AND jsonb_typeof(pol.analytic_distribution) = 'object'
                  AND NOT EXISTS (
                      SELECT 1 FROM employee_purchase_requisition pr
                      WHERE (po.requisition_order = pr.name
                             OR po.pr_number = pr.name
                             OR po.origin = pr.name)
                        AND pr.state NOT IN ('draft', 'cancel', 'cancelled', 'rejected')
                  )

                UNION ALL

                -- Reserved: Unbilled Confirmed POs
                SELECT
                    'reserved' as entry_type,
                    po.name as name,
                    ((pol.qty_to_invoice * pol.price_unit)
                     * CAST(dist.value AS numeric) / 100.0) as amount,
                    0.0 as budget_amt,
                    0.0 as actual_amt,
                    -((pol.qty_to_invoice * pol.price_unit)
                      * CAST(dist.value AS numeric) / 100.0) as remaining_amt,
                    0.0 as utilization,
                    COALESCE(po.payment_date, po.date_order::date) as date,
                    po.company_id as company_id,
                    wbl.id as budget_line_id,
                    wbl.plan_id as plan_id,
                    wbl.analytic_account_id as analytic_account_id,
                    wbl.department_id as department_id,
                    wbl.project_id as project_id,
                    wbl.category as category
                FROM purchase_order_line pol
                JOIN purchase_order po ON pol.order_id = po.id
                CROSS JOIN jsonb_each_text(pol.analytic_distribution) AS dist(key, value)
                JOIN monthly_budget_plan wbp ON
                    COALESCE(po.payment_date, po.date_order::date) >= wbp.date_from AND
                    COALESCE(po.payment_date, po.date_order::date) <= wbp.date_to AND
                    wbp.company_id = po.company_id AND
                    wbp.state = 'confirmed'
                JOIN monthly_budget_line wbl ON
                     wbl.plan_id = wbp.id AND
                     wbl.analytic_account_id::text = dist.key
                WHERE po.state IN ('purchase', 'done')
                  AND pol.qty_to_invoice > 0
                  AND pol.analytic_distribution IS NOT NULL
                  AND jsonb_typeof(pol.analytic_distribution) = 'object'

                UNION ALL

                -- Fixed: Confirmed Fixed Costs
                SELECT
                    'fixed' as entry_type,
                    fc.name as name,
                    fc.amount as amount,
                    0.0 as budget_amt,
                    0.0 as actual_amt,
                    -fc.amount as remaining_amt,
                    0.0 as utilization,
                    wbp.date_from as date,
                    fc.company_id as company_id,
                    wbl.id as budget_line_id,
                    fc.plan_id as plan_id,
                    fc.analytic_account_id as analytic_account_id,
                    fc.department_id as department_id,
                    fc.project_id as project_id,
                    fc.category as category
                FROM monthly_budget_fixed_cost fc
                JOIN monthly_budget_plan wbp ON fc.plan_id = wbp.id
                LEFT JOIN monthly_budget_line wbl ON
                     wbl.plan_id = wbp.id AND
                     wbl.analytic_account_id = fc.analytic_account_id AND
                     wbl.department_id IS NOT DISTINCT FROM fc.department_id AND
                     wbl.project_id IS NOT DISTINCT FROM fc.project_id AND
                     wbl.category IS NOT DISTINCT FROM fc.category
                WHERE fc.state = 'confirmed' AND wbp.state = 'confirmed'
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
    def get_dashboard_data(self, filters=None):
        """Fetch summarized data for the OWL dashboard components using SQL aggregation."""
        if filters is None:
            filters = {}

        # 1. Resolve Plans based on year/month/company
        domain = [('state', '=', 'confirmed')]
        if filters.get('company_id'):
            domain.append(('company_id', '=', int(filters['company_id'])))
        
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
                SUM(CASE WHEN mbr.entry_type = 'fixed' THEN mbr.amount ELSE 0 END) AS fixed,
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
            fixed = r['fixed'] or 0.0
            reserved = r['reserved'] or 0.0
            used = r['used'] or 0.0
            
            # The prompt explicitly asks for: available = budget - fixed - reserved - used
            available = budget - fixed - reserved - used
            utilization = (fixed + reserved + used) / budget if budget else 0.0

            result.append({
                'analytic': analytics.get(r['analytic_account_id'], 'General'),
                'department': depts.get(r['department_id'], '-'),
                'project': projs.get(r['project_id'], '-'),
                'category': r['category'] or '-',
                'budget': budget,
                'fixed': fixed,
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
                # Create a composite label if there's no project/department to keep it readable, 
                # but analytic is the primary dimension as per prompt.
                'label': f"{d['analytic']} {d['department'] if d['department'] != '-' else ''}".strip(),
                'budget': d['budget'],
                'fixed': d['fixed'],
                'reserved': d['reserved'],
                'used': d['used'],
            }
            for d in breakdown_data
            if d['budget'] > 0 or d['fixed'] > 0 or d['reserved'] > 0 or d['used'] > 0
        ]

    def _get_kpi(self, breakdown_data):
        total_budget = sum(d['budget'] for d in breakdown_data)
        total_fixed = sum(d['fixed'] for d in breakdown_data)
        total_reserved = sum(d['reserved'] for d in breakdown_data)
        total_used = sum(d['used'] for d in breakdown_data)
        total_available = total_budget - total_fixed - total_reserved - total_used
        utilization = (total_fixed + total_reserved + total_used) / total_budget * 100 if total_budget else 0.0
        burn_rate = total_used / total_budget if total_budget else 0.0

        return {
            'total_budget': total_budget,
            'fixed_cost': total_fixed,
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
            {'label': 'Fixed Cost', 'value': -kpi['fixed_cost']},
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
