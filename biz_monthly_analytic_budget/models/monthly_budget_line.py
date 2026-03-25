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
        compute='_compute_reserved_amount',
        store=False,
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
                    (line.reserved_amount + line.used_amount) / line.budget_amount * 100.0
                )
            else:
                line.utilization_rate = 0.0

    @api.depends('plan_id.state', 'plan_id.date_from', 'plan_id.date_to', 'plan_id.company_id')
    def _compute_used_amount(self):
        """Compute used amount: posted Vendor Bills minus Vendor Credit Notes for this analytic."""
        for line in self:
            if not line.plan_id.date_from or not line.plan_id.date_to or not line.analytic_account_id:
                line.used_amount = 0.0
                continue

            domain = [
                ('move_id.move_type', 'in', ('in_invoice', 'in_refund')),
                ('move_id.state', '=', 'posted'),
                ('company_id', '=', line.company_id.id),
                ('date', '>=', line.plan_id.date_from),
                ('date', '<=', line.plan_id.date_to),
                ('analytic_distribution', '!=', False)
            ]
            
            bill_lines = self.env['account.move.line'].sudo().search(domain)
            
            total_used = 0.0
            analytic_str = str(line.analytic_account_id.id)
            for bline in bill_lines:
                dist = bline.analytic_distribution or {}
                if analytic_str in dist:
                    pct = dist[analytic_str] or 0.0
                    amt = bline.price_subtotal if bline.move_id.move_type == 'in_invoice' else -bline.price_subtotal
                    total_used += amt * (pct / 100.0)

            line.used_amount = total_used

    @api.depends('plan_id.state', 'plan_id.date_from', 'plan_id.date_to', 'plan_id.company_id')
    def _compute_reserved_amount(self):
        """
        Compute total budget reserved from:
          1. Non-draft PRs whose payment_date falls in the month.
          2. Draft POs (RFQs) NOT linked to any active PR.
          3. Confirmed POs (unbilled amount) NOT linked to any active PR.
        Only sums analytic_distribution allocated to this line's analytic_account_id.
        """
        valid_lines = self.filtered(lambda l: l.plan_id.date_from and l.plan_id.date_to and l.analytic_account_id)
        for line in self - valid_lines:
            line.reserved_amount = 0.0
        
        if not valid_lines:
            return

        all_date_froms = valid_lines.mapped('plan_id.date_from')
        all_date_tos = valid_lines.mapped('plan_id.date_to')
        global_date_from = min(all_date_froms)
        global_date_to = max(all_date_tos)
        company_ids = valid_lines.mapped('company_id.id')

        # Batch fetch PRs
        all_prs = self.env['employee.purchase.requisition'].sudo().search([
            ('state', 'not in', ('draft', 'cancel', 'cancelled', 'rejected')),
            ('payment_date', '>=', global_date_from),
            ('payment_date', '<=', global_date_to),
            ('company_id', 'in', company_ids),
        ])

        # Batch fetch Confirmed POs
        global_dt_from = fields.Datetime.to_datetime(global_date_from)
        global_dt_to = fields.Datetime.to_datetime(global_date_to).replace(hour=23, minute=59, second=59)
        all_confirmed_pos = self.env['purchase.order'].sudo().search([
            ('state', 'in', ['purchase', 'done']),
            '|',
            '&', ('payment_date', '>=', global_date_from),
                 ('payment_date', '<=', global_date_to),
            '&', ('payment_date', '=', False),
                 '&', ('date_order', '>=', global_dt_from),
                      ('date_order', '<=', global_dt_to),
            ('company_id', 'in', company_ids),
        ])

        # Batch fetch Draft POs (RFQs)
        all_rfqs = self.env['purchase.order'].sudo().search([
            ('state', '=', 'draft'),
            ('payment_date', '>=', global_date_from),
            ('payment_date', '<=', global_date_to),
            ('company_id', 'in', company_ids),
        ])

        # Maps PR name -> POs
        po_linked_pr_names = set()
        for po in self.env['purchase.order'].sudo().search([('state', 'in', ['purchase', 'done'])]):
            req_order = (getattr(po, 'requisition_order', '') or '').strip()
            pr_number = (getattr(po, 'pr_number', '') or '').strip()
            origin = (po.origin or '').strip()
            for val in (req_order, pr_number, origin):
                if val:
                    po_linked_pr_names.add(val)

        for line in valid_lines:
            date_from = line.plan_id.date_from
            date_to = line.plan_id.date_to
            analytic_str = str(line.analytic_account_id.id)
            comp_id = line.company_id.id

            def _get_analytic_amt(lines2):
                amt = 0.0
                for l in lines2:
                    dist = l.analytic_distribution or {}
                    if analytic_str in dist:
                        pct = dist[analytic_str] or 0.0
                        amt += l.price_subtotal * (pct / 100.0)
                return amt

            # 1. PRs
            line_prs = all_prs.filtered(lambda pr: date_from <= pr.payment_date <= date_to and pr.company_id.id == comp_id)
            pr_amount = 0.0
            active_pr_names = set()
            for pr in line_prs:
                if pr.name in po_linked_pr_names:
                    continue
                pr_amount += _get_analytic_amt(pr.requisition_order_ids)
                active_pr_names.add(pr.name)

            def _po_linked(po):
                req_order = (getattr(po, 'requisition_order', '') or '').strip()
                pr_number = (getattr(po, 'pr_number', '') or '').strip()
                if req_order in active_pr_names or pr_number in active_pr_names:
                    return True
                origin = (po.origin or '').strip()
                if origin and origin in active_pr_names:
                    return True
                return False

            # 2. RFQs
            rfq_amount = 0.0
            for po in all_rfqs.filtered(lambda p: date_from <= p.payment_date <= date_to and p.company_id.id == comp_id):
                if _po_linked(po):
                    continue
                rfq_amount += _get_analytic_amt(po.order_line)

            # 3. Confirmed POs
            po_unbilled_amount = 0.0
            line_dt_from = fields.Datetime.to_datetime(date_from)
            line_dt_to = fields.Datetime.to_datetime(date_to).replace(hour=23, minute=59, second=59)
            for po in all_confirmed_pos.filtered(lambda p: p.company_id.id == comp_id):
                if po.payment_date:
                    if not (date_from <= po.payment_date <= date_to):
                        continue
                else:
                    if not (po.date_order and line_dt_from <= po.date_order <= line_dt_to):
                        continue
                if _po_linked(po):
                    continue
                
                # Unbilled logic for specific analytic lines using exact native unbilled qty
                for pol in po.order_line:
                    dist = pol.analytic_distribution or {}
                    if analytic_str in dist:
                        pct = dist[analytic_str] or 0.0
                        po_unbilled_amount += (pol.qty_to_invoice * pol.price_unit) * (pct / 100.0)

            line.reserved_amount = pr_amount + rfq_amount + po_unbilled_amount

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

    # ── Budget update helpers (deprecated since now computed) ──────

    def _add_reservation(self, amount):
        pass

    def _release_reservation(self, amount):
        pass

    def _consume_reservation(self, amount):
        pass
