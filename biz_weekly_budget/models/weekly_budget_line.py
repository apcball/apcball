# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class WeeklyBudgetLine(models.Model):
    _name = 'weekly.budget.line'
    _description = 'Weekly Budget Line'
    _order = 'date_from asc'

    plan_id = fields.Many2one(
        'weekly.budget.plan',
        string='Budget Plan',
        required=True,
        ondelete='cascade',
        index=True,
    )
    name = fields.Char(string='Week Label', required=True)
    week_number = fields.Integer(string='Week #')
    date_from = fields.Date(string='Date From', required=True, index=True)
    date_to = fields.Date(string='Date To', required=True, index=True)
    amount_limit = fields.Float(string='Budget Limit', required=True)
    amount_used = fields.Float(
        string='Used Amount',
        compute='_compute_amount_used',
        store=True,
    )
    amount_reserved = fields.Float(
        string='Reserved Amount',
        compute='_compute_amount_reserved',
        store=True,
        help='Total tentative budget reserved from non-draft PRs, MRs, and standalone RFQs.',
    )
    amount_available = fields.Float(
        string='Available',
        compute='_compute_remaining',
        store=True,
        help='Budget Limit minus Used and Reserved amounts.',
    )
    amount_remaining = fields.Float(
        string='Remaining (vs Used)',
        compute='_compute_remaining',
        store=True,
    )
    usage_percentage = fields.Float(
        string='Usage %',
        compute='_compute_remaining',
        store=True,
    )
    status = fields.Selection([
        ('normal', 'Normal'),
        ('exceeded', 'Exceeded'),
    ], string='Status', compute='_compute_remaining', store=True)

    currency_id = fields.Many2one(
        related='plan_id.currency_id',
        string='Currency',
        store=True,
    )
    company_id = fields.Many2one(
        related='plan_id.company_id',
        string='Company',
        store=True,
    )
    all_companies = fields.Boolean(
        related='plan_id.all_companies',
        string='All Companies',
        store=True,
    )
    plan_state = fields.Selection(
        related='plan_id.state',
        string='Plan Status',
        store=True,
    )

    # History tracking
    history_ids = fields.One2many(
        'weekly.budget.line.history',
        'line_id',
        string='Adjustment History',
    )

    def _get_company_domain(self):
        """Return company domain filter for this budget line."""
        if self.plan_id.all_companies:
            return []
        elif self.plan_id.company_id:
            return [('company_id', '=', self.plan_id.company_id.id)]
        return []

    @api.depends('date_from', 'date_to', 'plan_id.company_id',
                 'plan_id.all_companies', 'plan_id.state')
    def _compute_amount_used(self):
        """Compute net used amount: posted Vendor Bills minus Vendor Credit Notes due this week."""
        for line in self:
            if not line.date_from or not line.date_to:
                line.amount_used = 0.0
                continue

            company_domain = []
            if not line.plan_id.all_companies and line.plan_id.company_id:
                company_domain = [('company_id', '=', line.plan_id.company_id.id)]

            date_domain = [
                ('state', '=', 'posted'),
                ('invoice_date_due', '>=', line.date_from),
                ('invoice_date_due', '<=', line.date_to),
            ]

            # Vendor Bills
            bills = self.env['account.move'].sudo().search(
                [('move_type', '=', 'in_invoice')] + date_domain + company_domain
            )
            total_bills = sum(bills.mapped('amount_total'))

            # Vendor Credit Notes (ใบลดหนี้ — deducted from used)
            credit_notes = self.env['account.move'].sudo().search(
                [('move_type', '=', 'in_refund')] + date_domain + company_domain
            )
            total_credit = sum(credit_notes.mapped('amount_total'))

            line.amount_used = max(0.0, total_bills - total_credit)

    @api.depends('date_from', 'date_to', 'plan_id.company_id',
                 'plan_id.all_companies', 'plan_id.state')
    def _compute_amount_reserved(self):
        """
        Compute total budget reserved from:
          1. Non-draft PRs whose payment_date falls in week
          2. Non-draft MRs whose payment_date falls in week
          3. Draft POs (RFQs) NOT linked to any active PR or MR
          4. Confirmed POs (unbilled amount) NOT linked to any active PR or MR

        Key: each source document is counted EXACTLY ONCE. When a PR/MR has
        a confirmed PO, only the PO's unbilled amount is counted (the PR/MR
        is excluded to avoid double counting).

        Performance: all DB queries are batched once across the full date span
        of the entire recordset, then filtered in-memory per line to avoid
        N×queries pattern.
        """
        # ── Guard: handle empty/incomplete lines first ──────────────────────
        valid_lines = self.filtered(lambda l: l.date_from and l.date_to)
        for line in self - valid_lines:
            line.amount_reserved = 0.0
        if not valid_lines:
            return

        # ── Compute global date span & company scope ────────────────────────
        all_date_froms = valid_lines.mapped('date_from')
        all_date_tos = valid_lines.mapped('date_to')
        global_date_from = min(all_date_froms)
        global_date_to = max(all_date_tos)

        # Determine company scope: union of all companies in the recordset
        has_all_companies = any(l.plan_id.all_companies for l in valid_lines)
        company_ids = list({
            l.plan_id.company_id.id
            for l in valid_lines
            if not l.plan_id.all_companies and l.plan_id.company_id
        })

        def _company_domain(field='company_id'):
            if has_all_companies:
                return []
            return [(field, 'in', company_ids)] if company_ids else []

        # ── Batch fetch: PRs across full span ───────────────────────────────
        all_prs = self.env['employee.purchase.requisition'].sudo().search(
            [
                ('state', '!=', 'draft'),
                ('payment_date', '>=', global_date_from),
                ('payment_date', '<=', global_date_to),
            ] + _company_domain()
        )

        # ── Batch fetch: MRs across full span ───────────────────────────────
        all_mrs = self.env['material.requisition'].sudo().search(
            [
                ('state', '!=', 'draft'),
                ('payment_date', '>=', global_date_from),
                ('payment_date', '<=', global_date_to),
            ] + _company_domain()
        )
        # Pre-build MR name→id lookup once for origin-matching
        global_mr_name_to_id = {mr.name: mr.id for mr in all_mrs}

        # ── Batch fetch: ALL confirmed POs (for PR/MR exclusion logic) ──────
        # No date filter here — we need to know if any confirmed PO references
        # any PR/MR in our span, regardless of when the PO was confirmed.
        all_confirmed_pos = self.env['purchase.order'].sudo().search(
            [('state', 'in', ['purchase', 'done'])] + _company_domain()
        )

        # ── Batch fetch: RFQs (draft POs) across full span ──────────────────
        all_rfqs = self.env['purchase.order'].sudo().search(
            [
                ('state', '=', 'draft'),
                ('payment_date', '>=', global_date_from),
                ('payment_date', '<=', global_date_to),
            ] + _company_domain()
        )

        # ── Batch fetch: confirmed POs with payment/order date in full span ──
        global_dt_from = fields.Datetime.to_datetime(global_date_from)
        global_dt_to = fields.Datetime.to_datetime(global_date_to).replace(
            hour=23, minute=59, second=59
        )
        all_week_confirmed_pos = self.env['purchase.order'].sudo().search(
            [
                ('state', 'in', ['purchase', 'done']),
                '|',
                '&', ('payment_date', '>=', global_date_from),
                     ('payment_date', '<=', global_date_to),
                '&', ('payment_date', '=', False),
                     '&', ('date_order', '>=', global_dt_from),
                          ('date_order', '<=', global_dt_to),
            ] + _company_domain()
        )

        # ── Pre-build confirmed-PO → PR/MR link maps (done once globally) ───
        # Maps: pr_name → True/False (has a confirmed PO), mr_id → True/False
        global_po_linked_pr_names = set()
        global_po_linked_mr_ids = set()
        for po in all_confirmed_pos:
            req_order = (getattr(po, 'requisition_order', '') or '').strip()
            pr_number = (getattr(po, 'pr_number', '') or '').strip()
            origin = (po.origin or '').strip()
            for val in (req_order, pr_number, origin):
                if val:
                    global_po_linked_pr_names.add(val)
            mr_link = getattr(po, 'material_requisition_id', False)
            if mr_link:
                global_po_linked_mr_ids.add(mr_link.id)
            if origin and origin in global_mr_name_to_id:
                global_po_linked_mr_ids.add(global_mr_name_to_id[origin])

        # ── Per-line computation: pure in-memory filtering (no DB queries) ──
        for line in valid_lines:
            date_from = line.date_from
            date_to = line.date_to
            line_company_id = (
                line.plan_id.company_id.id
                if not line.plan_id.all_companies
                else False
            )

            def _match_company(rec):
                if line.plan_id.all_companies:
                    return True
                return rec.company_id.id == line_company_id

            # Filter PRs / MRs for this specific week & company
            line_prs = all_prs.filtered(
                lambda pr: pr.payment_date
                and date_from <= pr.payment_date <= date_to
                and _match_company(pr)
            )
            line_mrs = all_mrs.filtered(
                lambda mr: mr.payment_date
                and date_from <= mr.payment_date <= date_to
                and _match_company(mr)
            )

            pr_name_set = {pr.name for pr in line_prs}
            mr_name_to_id = {mr.name: mr.id for mr in line_mrs}
            mr_id_set = set(mr_name_to_id.values())

            # Determine excluded PRs/MRs (those that already have a confirmed PO)
            # We use the globally pre-built sets and intersect with this line's scope
            excluded_pr_names = pr_name_set & global_po_linked_pr_names
            excluded_mr_ids = mr_id_set & global_po_linked_mr_ids

            # ── 1. Non-draft PRs (excluding those with confirmed POs) ────────
            pr_amount = 0.0
            active_pr_names = set()
            for pr in line_prs:
                if pr.name in excluded_pr_names:
                    continue
                pr_amount += sum(pr.requisition_order_ids.mapped('price_subtotal'))
                active_pr_names.add(pr.name)

            # ── 2. Non-draft MRs (excluding those with confirmed POs) ────────
            mr_amount = 0.0
            active_mr_ids = set()
            active_mr_names = set()
            for mr in line_mrs:
                if mr.id in excluded_mr_ids:
                    continue
                mr_amount += (mr.total_cost or 0.0)
                active_mr_ids.add(mr.id)
                active_mr_names.add(mr.name)

            # ── 3. Standalone RFQs (draft POs not linked to active PR/MR) ───
            rfq_amount = 0.0
            for po in all_rfqs.filtered(
                lambda p: p.payment_date
                and date_from <= p.payment_date <= date_to
                and _match_company(p)
            ):
                if self._po_linked_to_active_pr_mr(
                    po, active_pr_names, active_mr_ids, active_mr_names
                ):
                    continue
                rfq_amount += po.amount_total

            # ── 4. Confirmed POs (Unbilled) in this week, not linked to PR/MR
            po_unbilled_amount = 0.0
            line_dt_from = fields.Datetime.to_datetime(date_from)
            line_dt_to = fields.Datetime.to_datetime(date_to).replace(
                hour=23, minute=59, second=59
            )
            for po in all_week_confirmed_pos.filtered(_match_company):
                # Additional in-week check (global fetch used wider span)
                if po.payment_date:
                    if not (date_from <= po.payment_date <= date_to):
                        continue
                else:
                    if not (po.date_order and line_dt_from <= po.date_order <= line_dt_to):
                        continue
                if self._po_linked_to_active_pr_mr(
                    po, active_pr_names, active_mr_ids, active_mr_names
                ):
                    continue
                po_unbilled_amount += po.remaining_to_bill

            line.amount_reserved = (
                pr_amount + mr_amount + rfq_amount + po_unbilled_amount
            )

    def _po_linked_to_active_pr_mr(self, po, active_pr_names, active_mr_ids, active_mr_names):
        """Check if a PO is linked to a PR or MR that is already counted as reserved."""
        # Check MR via M2O
        mr_id = getattr(po, 'material_requisition_id', False)
        if mr_id and mr_id.id in active_mr_ids:
            return True
        # Check PR via requisition_order / pr_number
        req_order = (getattr(po, 'requisition_order', '') or '').strip()
        pr_number = (getattr(po, 'pr_number', '') or '').strip()
        if req_order in active_pr_names or pr_number in active_pr_names:
            return True
        # Check origin against active PR or MR names
        origin = (po.origin or '').strip()
        if origin and origin in active_pr_names:
            return True
        if any(mr_name and mr_name in origin for mr_name in active_mr_names):
            return True
        return False

    @api.depends('amount_limit', 'amount_used', 'amount_reserved')
    def _compute_remaining(self):
        for line in self:
            line.amount_remaining = line.amount_limit - line.amount_used
            line.amount_available = line.amount_limit - line.amount_used - line.amount_reserved
            line.usage_percentage = (
                (line.amount_used / line.amount_limit * 100)
                if line.amount_limit else 0.0
            )
            line.status = 'exceeded' if line.amount_used > line.amount_limit else 'normal'

    def action_adjust_budget(self):
        """Open the budget adjustment wizard."""
        self.ensure_one()
        return {
            'name': _('Adjust Budget'),
            'type': 'ir.actions.act_window',
            'res_model': 'budget.adjustment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_line_id': self.id,
                'default_current_amount': self.amount_limit,
            },
        }

    def _invalidate_reserved(self):
        """Force recompute of amount_reserved for budget lines covering this date range."""
        self.invalidate_recordset(['amount_reserved'])
        self._compute_amount_reserved()


class WeeklyBudgetLineHistory(models.Model):
    _name = 'weekly.budget.line.history'
    _description = 'Budget Line Adjustment History'
    _order = 'create_date desc'

    line_id = fields.Many2one(
        'weekly.budget.line',
        string='Budget Line',
        required=True,
        ondelete='cascade',
    )
    user_id = fields.Many2one(
        'res.users',
        string='Adjusted By',
        default=lambda self: self.env.uid,
        readonly=True,
    )
    date = fields.Datetime(
        string='Date',
        default=fields.Datetime.now,
        readonly=True,
    )
    old_amount = fields.Float(string='Previous Amount', readonly=True)
    new_amount = fields.Float(string='New Amount', readonly=True)
    reason = fields.Text(string='Reason', readonly=True)
