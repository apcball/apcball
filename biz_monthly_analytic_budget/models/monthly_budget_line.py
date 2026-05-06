# -*- coding: utf-8 -*-
import logging
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

# Fallback matching strategies — ordered from most specific to most general
_BUDGET_MATCH_STRATEGIES = [
    ['analytic_account_id', 'department_id', 'project_id', 'category'],
    ['analytic_account_id', 'department_id', 'project_id'],
    ['analytic_account_id', 'department_id'],
    ['analytic_account_id', 'project_id', 'category'],
    ['analytic_account_id', 'project_id'],
    ['analytic_account_id', 'category'],
    ['analytic_account_id'],
]

class MonthlyBudgetLine(models.Model):
    """
    Line item inside a Monthly Budget Plan.
    Each line carries a budget allocation for a unique combination of:
      analytic_account + department + project + category (multi-dimensional key).
    Missing dimensions are treated as wildcards (blank = match-all fallback).
    """
    _name = 'monthly.budget.line'
    _description = 'Monthly Budget Line'
    _order = 'plan_id, analytic_account_id, department_id, project_id'

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
    department_id = fields.Many2one(
        'hr.department',
        string='Department',
        index=True,
        help='Optional: restrict this budget line to a specific department.',
    )
    project_id = fields.Many2one(
        'project.project',
        string='Project',
        index=True,
        help='Optional: restrict this budget line to a specific project.',
    )
    category = fields.Selection(
        selection=[
            ('capex', 'งบลงทุน (CapEx)'),
            ('opex', 'งบดำเนินงาน (OpEx)'),
        ],
        string='Category',
        index=True,
        help='Optional: CapEx or OpEx budget segregation.',
    )
    dimension_key = fields.Char(
        string='Dimension Key',
        compute='_compute_dimension_key',
        store=True,
        index=True,
        help='Normalized composite key used to enforce uniqueness across all dimensions.',
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
        compute='_compute_reserved_amount',
        store=False,
    )
    carried_amount = fields.Monetary(
        string='Carried Forward',
        currency_field='currency_id',
        default=0.0,
        help='Budget amount carried forward from previous month',
    )
    used_amount = fields.Monetary(
        string='Used',
        currency_field='currency_id',
        compute='_compute_used_amount',
        store=False,
    )
    available_amount = fields.Monetary(
        string='Available',
        currency_field='currency_id',
        compute='_compute_available_amount',
        store=False,
    )
    utilization_rate = fields.Float(
        string='Utilization (%)',
        compute='_compute_available_amount',
        store=False,
        help='(Reserved + Used) / Budget Amount',
    )

    # ── Computed ─────────────────────────────────────────────────

    @api.depends(
        'plan_id', 'analytic_account_id',
        'department_id', 'project_id', 'category',
    )
    def _compute_dimension_key(self):
        for rec in self:
            rec.dimension_key = "|".join([
                str(rec.plan_id.id or ''),
                str(rec.analytic_account_id.id or ''),
                str(rec.department_id.id or ''),
                str(rec.project_id.id or ''),
                str(rec.category or ''),
            ])

    @api.depends('plan_id.total_budget', 'percentage')
    def _compute_budget_amount(self):
        for line in self:
            line.budget_amount = line.plan_id.total_budget * line.percentage / 100.0

    @api.depends('budget_amount', 'carried_amount', 'reserved_amount', 'used_amount')
    def _compute_available_amount(self):
        for line in self:
            total_budget = line.budget_amount + line.carried_amount
            line.available_amount = total_budget - line.reserved_amount - line.used_amount
            if total_budget:
                line.utilization_rate = (
                    (line.reserved_amount + line.used_amount) / total_budget
                )
            else:
                line.utilization_rate = 0.0

    @api.depends('plan_id.state', 'plan_id.date_from', 'plan_id.date_to', 'plan_id.company_id')
    def _compute_used_amount(self):
        """Compute used amount from monthly budget commitments in used state."""
        valid_lines = self.filtered(lambda l: l.plan_id.date_from and l.plan_id.date_to and l.analytic_account_id)
        for line in self - valid_lines:
            line.used_amount = 0.0

        if not valid_lines:
            return

        company_ids = valid_lines.mapped('company_id.id')
        all_date_froms = valid_lines.mapped('plan_id.date_from')
        all_date_tos = valid_lines.mapped('plan_id.date_to')
        global_date_from = min(all_date_froms)
        global_date_to = max(all_date_tos)

        commitments = self.env['budget.commitment'].sudo().search([
            ('budget_source', '=', 'monthly'),
            ('state', '=', 'used'),
            ('company_id', 'in', company_ids),
            ('date', '>=', global_date_from),
            ('date', '<=', global_date_to),
        ])

        committed_totals = defaultdict(float)
        for commitment in commitments:
            if not commitment.analytic_account_id or not commitment.date:
                continue
            committed_totals[(
                commitment.company_id.id,
                commitment.analytic_account_id.id,
                commitment.date,
            )] += commitment.amount

        result_map = {}
        for line in valid_lines:
            date_from = line.plan_id.date_from
            date_to = line.plan_id.date_to
            comp_id = line.company_id.id
            used = 0.0
            for (commit_company_id, analytic_id, commit_date), amount in committed_totals.items():
                if commit_company_id != comp_id:
                    continue
                if analytic_id != line.analytic_account_id.id:
                    continue
                if date_from <= commit_date <= date_to:
                    used += amount
            result_map[line.id] = used

        for line in valid_lines:
            line.used_amount = result_map.get(line.id, 0.0)

    @api.depends('plan_id.state', 'plan_id.date_from', 'plan_id.date_to', 'plan_id.company_id')
    def _compute_reserved_amount(self):
        """
        Compute total budget reserved from monthly commitment records.

        Reservation is now driven by the document lifecycle:
          - PR head approval creates a reserved commitment
          - direct RFQ / draft PO creates a reserved commitment
          - draft vendor bill creates a reserved commitment

        This keeps the budget line in sync with the actual reserved audit trail
        instead of inferring reservations from document state alone.
        """
        valid_lines = self.filtered(lambda l: l.plan_id.date_from and l.plan_id.date_to and l.analytic_account_id)
        for line in self - valid_lines:
            line.reserved_amount = 0.0

        if not valid_lines:
            return

        company_ids = valid_lines.mapped('company_id.id')
        all_date_froms = valid_lines.mapped('plan_id.date_from')
        all_date_tos = valid_lines.mapped('plan_id.date_to')
        global_date_from = min(all_date_froms)
        global_date_to = max(all_date_tos)

        commitments = self.env['budget.commitment'].sudo().search([
            ('budget_source', '=', 'monthly'),
            ('state', '=', 'reserved'),
            ('company_id', 'in', company_ids),
            ('date', '>=', global_date_from),
            ('date', '<=', global_date_to),
        ])

        committed_totals = defaultdict(float)
        for commitment in commitments:
            if not commitment.analytic_account_id or not commitment.date:
                continue
            committed_totals[(
                commitment.company_id.id,
                commitment.analytic_account_id.id,
                commitment.date,
            )] += commitment.amount

        for line in valid_lines:
            date_from = line.plan_id.date_from
            date_to = line.plan_id.date_to
            comp_id = line.company_id.id
            reserved = 0.0
            for (commit_company_id, analytic_id, commit_date), amount in committed_totals.items():
                if commit_company_id != comp_id:
                    continue
                if analytic_id != line.analytic_account_id.id:
                    continue
                if date_from <= commit_date <= date_to:
                    reserved += amount

            line.reserved_amount = reserved

    # ── Constraints ──────────────────────────────────────────────

    _sql_constraints = [
        (
            'unique_dimension_key',
            'UNIQUE(dimension_key)',
            'A budget line with this exact combination of analytic account, '
            'department, project, and category already exists for this plan.',
        ),
    ]

    @api.constrains('percentage')
    def _check_percentage(self):
        for line in self:
            if line.percentage < 0 or line.percentage > 100:
                raise ValidationError(_('Percentage must be between 0 and 100.'))

    # ── Budget Matching Engine ───────────────────────────────────

    @api.model
    def _extract_budget_dimensions(self, line):
        """
        Extract budget dimension values from a transaction line (PR line or PO line).
        Returns a dict of dimension field name → value (id or selection value).
        Only fields that actually exist on the line model are extracted.
        """
        dims = {
            'analytic_account_id': None,
            'department_id': None,
            'project_id': None,
            'category': None,
        }
        if hasattr(line, 'analytic_account_id'):
            dims['analytic_account_id'] = line.analytic_account_id.id or None
        if hasattr(line, 'department_id'):
            dims['department_id'] = line.department_id.id or None
        if hasattr(line, 'project_id'):
            dims['project_id'] = line.project_id.id or None
        if hasattr(line, 'category'):
            dims['category'] = line.category or None
        return dims

    @api.model
    def _build_budget_domain(self, plan, dims, fields_to_use):
        """
        Build an ORM domain for budget line lookup using the given subset of dimension fields.

        :param plan: monthly.budget.plan record
        :param dims: dict of dimension values (from _extract_budget_dimensions)
        :param fields_to_use: list of field names to include in domain
        :returns: list of domain tuples
        """
        domain = [('plan_id', '=', plan.id)]
        for f in fields_to_use:
            val = dims.get(f)
            if val:
                domain.append((f, '=', val))
            else:
                domain.append((f, '=', False))
        return domain

    @api.model
    def _find_budget_line(self, plan, dims, log_fallback=True):
        """
        Find the best-matching budget line using priority fallback strategy.

        Strategies (ordered most → least specific):
          1. analytic + department + project + category  (exact)
          2. analytic + department + project
          3. analytic + department
          4. analytic + project + category
          5. analytic + project
          6. analytic + category
          7. analytic only                               (global fallback)

        :param plan: monthly.budget.plan record
        :param dims: dict {field_name: value_or_None} from _extract_budget_dimensions
        :param log_fallback: whether to log when a non-exact strategy is used
        :returns: monthly.budget.line record or empty recordset
        """
        for i, strategy_fields in enumerate(_BUDGET_MATCH_STRATEGIES):
            domain = [('plan_id', '=', plan.id)]
            for f in strategy_fields:
                val = dims.get(f)
                if val:
                    domain.append((f, '=', val))
                else:
                    domain.append((f, '=', False))
            line = self.search(domain, limit=1)
            if line:
                if i > 0 and log_fallback:
                    _logger.info(
                        'monthly.budget.line: fallback match at strategy #%d (%s) '
                        'for plan=%s dims=%s → line=%s',
                        i + 1, strategy_fields, plan.name, dims, line.id,
                    )
                return line
        return self.browse()

    # ── Concurrency: Row-level locking ───────────────────────────

    @api.model
    def _lock_budget_lines(self, analytic_account_ids, plan_id):
        """
        Acquire PostgreSQL row-level lock (FOR UPDATE) on budget lines
        matching the given analytic accounts and plan before any mutation.
        MUST be called inside a transaction, and data MUST be re-read after.
        """
        if not analytic_account_ids:
            return
        query = """
            SELECT id FROM monthly_budget_line
            WHERE analytic_account_id = ANY(%s)
            AND plan_id = %s
            FOR UPDATE
        """
        self.env.cr.execute(query, (list(analytic_account_ids), plan_id))
        _logger.debug(
            'monthly.budget.line: acquired FOR UPDATE lock on plan_id=%s, analytic_ids=%s',
            plan_id, analytic_account_ids,
        )

    # ── Analytic Distribution Precision (Decimal) ────────────────

    @api.model
    def _normalize_distribution(self, distribution):
        """
        Normalize analytic distribution so percentages sum to 100.
        Uses ``decimal.Decimal`` for precision. Rejects zero-sum distributions.

        :param distribution: dict {str(analytic_id): float_percentage}
        :returns: dict {str(analytic_id): Decimal percentage (normalized to 100)}
        """
        if not distribution:
            raise UserError(_("Analytic distribution cannot be empty."))

        total = sum(Decimal(str(v)) for v in distribution.values())
        if total == 0:
            raise UserError(_("Analytic distribution total cannot be zero."))

        normalized = {}
        for acc_id, value in distribution.items():
            pct = (Decimal(str(value)) / total) * Decimal('100')
            normalized[acc_id] = pct.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
        return normalized

    @api.model
    def _compute_distribution_amount(self, total_amount, distribution):
        """
        Convert normalized analytic distribution to exact monetary amounts.

        :param total_amount: total monetary amount (float or Decimal)
        :param distribution: raw dict {str(analytic_id): float_percentage}
        :returns: dict {str(analytic_id): Decimal amount}
        """
        normalized = self._normalize_distribution(distribution)
        result = {}
        for acc_id, pct in normalized.items():
            amount = (Decimal(str(total_amount)) * pct / Decimal('100'))
            result[acc_id] = amount.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
        return result

    # ── Reserved vs Used Consistency (Single Source of Truth) ───

    def _recompute_line_balance(self):
        """
        Force re-evaluation of all live computed fields (reserved, used,
        available, utilization) by calling the compute methods directly.

        The fields are not stored, so we refresh them in memory instead of
        relying on cache invalidation side effects.
        """
        if not self:
            return
        self._compute_reserved_amount()
        self._compute_used_amount()
        self._compute_available_amount()
        for line in self:
            _logger.info(
                'monthly.budget.line [%s]: refreshed reserved=%.4f used=%.4f available=%.4f',
                line.id, line.reserved_amount, line.used_amount, line.available_amount,
            )
