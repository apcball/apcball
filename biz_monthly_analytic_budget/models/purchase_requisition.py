# -*- coding: utf-8 -*-
import logging
from datetime import timedelta
from decimal import Decimal
from markupsafe import escape
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

from .budget_utils import (
    RESERVED_PR_STATES,
    collect_analytic_ids_from_lines,
    extract_analytic_amounts,
    find_active_monthly_plans,
    get_first_plan_from_groups,
    format_ignored_analytic_accounts_message,
    format_missing_budget_line_message,
    format_no_analytic_distribution_message,
    split_analytic_totals_by_plan,
)

_logger = logging.getLogger(__name__)


class EmployeePurchaseRequisitionMonthly(models.Model):
    """
    Extend employee.purchase.requisition with monthly analytic budget validation.
    Budget check happens at head approval stage.
    """
    _inherit = 'employee.purchase.requisition'

    payment_date = fields.Date(
        string="Expected Payment",
        compute="_compute_payment_date",
        inverse="_inverse_payment_date",
        store=True,
        readonly=False
    )
    payment_date_manual = fields.Date(
        string="Manual Expected Payment",
        copy=False,
    )

    monthly_budget_check_result = fields.Html(
        string='Monthly Budget Check',
        compute='_compute_monthly_budget_check',
    )

    buz_budget_approval_id = fields.Many2one(
        'buz.monthly.budget.approval.request',
        string='Monthly Budget Approval Request',
        compute='_compute_budget_approval_id',
        store=False,
    )
    buz_budget_approval_state = fields.Selection(
        related='buz_budget_approval_id.state',
        string='Monthly Budget Approval Status',
    )
    budget_warning = fields.Boolean(
        string='Budget Warning',
        compute='_compute_monthly_budget_check'
    )
    is_budget_reserved = fields.Boolean(
        string='Budget Reserved',
        compute='_compute_is_budget_reserved',
    )

    @api.depends('state')
    def _compute_is_budget_reserved(self):
        Commitment = self.env['budget.commitment'].sudo()
        for req in self:
            if req.state in RESERVED_PR_STATES:
                has_commitment = Commitment.search([
                    ('document_model', '=', req._name),
                    ('document_id', '=', req.id),
                    ('state', 'in', ('reserved', 'used')),
                    ('budget_source', '=', 'monthly')
                ], limit=1)
                req.is_budget_reserved = bool(has_commitment)
            else:
                req.is_budget_reserved = False

    def _compute_budget_approval_id(self):
        ApprovalReq = self.env['buz.monthly.budget.approval.request'].sudo()
        for rec in self:
            req = ApprovalReq.search([
                ('document_type', '=', 'pr'),
                ('ref_pr_id', '=', rec.id),
            ], limit=1, order='id desc')
            rec.buz_budget_approval_id = req

    def _get_request_open_date(self):
        """Return the PR open/request date used as the budget reference date."""
        if self.request_date:
            return self.request_date
        if self.create_date:
            return self.create_date.date()
        return fields.Date.context_today(self)

    def _get_effective_vendor(self):
        self.ensure_one()
        if hasattr(self, 'purchase_vendor_id') and self.purchase_vendor_id:
            return self.purchase_vendor_id
        if self.vendor_id:
            return self.vendor_id

        line_vendors = self.requisition_order_ids.mapped('partner_id')
        line_vendors = line_vendors.filtered(lambda partner: partner)
        if len(line_vendors) == 1:
            return line_vendors
        return self.env['res.partner']

    def _get_auto_payment_date(self):
        self.ensure_one()
        vendor = self._get_effective_vendor()
        payment_term = vendor.property_supplier_payment_term_id
        p_date = self._get_request_open_date()
        if payment_term:
            if hasattr(payment_term, 'compute'):
                res = payment_term.compute(value=1, date_ref=p_date)
                if res and res[0] and res[0][0]:
                    return res[0][0]
            elif hasattr(payment_term, '_compute_terms'):
                try:
                    res = payment_term._compute_terms(
                        date_ref=p_date,
                        currency=self.company_id.currency_id,
                        company=self.company_id,
                        taxes_and_subtotals=[{'name': '', 'tax_amount': 0.0, 'base_amount': 1.0}],
                        untaxed_amount=1.0,
                        empty_taxes=True,
                        sign=1
                    )
                    if res and getattr(res, 'get', None) and res.get('line_ids'):
                        lines = res.get('line_ids')
                        return lines[-1].get('date') if lines else p_date
                    if res and isinstance(res, list):
                        return res[-1].get('date') if res else p_date
                except Exception as e:
                    _logger.warning("biz_monthly_analytic_budget _compute_terms failed: %s", e)

            max_days = 0
            for line in payment_term.line_ids:
                days = getattr(line, 'days', getattr(line, 'nb_days', 0))
                months = getattr(line, 'months', 0)
                total_days = (months * 30) + days
                if total_days > max_days:
                    max_days = total_days
            if max_days > 0:
                return p_date + timedelta(days=max_days)

        return p_date + timedelta(days=30)

    @api.depends(
        'requisition_deadline',
        'request_date',
        'vendor_id',
        'vendor_id.property_supplier_payment_term_id',
        'purchase_vendor_id',
        'purchase_vendor_id.property_supplier_payment_term_id',
        'requisition_order_ids.partner_id',
        'requisition_order_ids.partner_id.property_supplier_payment_term_id',
    )
    def _compute_payment_date(self):
        for req in self:
            if req.payment_date_manual:
                req.payment_date = req.payment_date_manual
                continue
            req.payment_date = req._get_auto_payment_date()

    def _inverse_payment_date(self):
        for req in self:
            auto_payment_date = req._get_auto_payment_date()
            req.payment_date_manual = False if req.payment_date == auto_payment_date else req.payment_date

    @api.onchange('payment_date')
    def _onchange_payment_date(self):
        for req in self:
            if not req.payment_date:
                req.payment_date_manual = False
                continue
            auto_payment_date = req._get_auto_payment_date()
            req.payment_date_manual = False if req.payment_date == auto_payment_date else req.payment_date

    @api.onchange('vendor_id', 'purchase_vendor_id', 'request_date', 'requisition_deadline', 'requisition_order_ids')
    def _onchange_payment_date_inputs(self):
        for req in self:
            if req.payment_date_manual:
                continue
            req.payment_date = req._get_auto_payment_date()

    # ── Computed preview ─────────────────────────────────────────

    @api.depends(
        'requisition_order_ids.price_subtotal',
        'requisition_order_ids.analytic_distribution',
        'payment_date',
    )
    def _compute_monthly_budget_check(self):
        for req in self:
            target_date = req.payment_date
            if not target_date or not req.requisition_order_ids:
                req.monthly_budget_check_result = ''
                req.budget_warning = False
                continue

            analytic_totals = {}  # {account_id: total_amount}
            for line in req.requisition_order_ids:
                for account_id, amount in extract_analytic_amounts(line):
                    analytic_totals[account_id] = analytic_totals.get(account_id, 0.0) + amount

            grouped_totals, ignored_totals = split_analytic_totals_by_plan(
                self.env, target_date, req.company_id.id, analytic_totals,
            )

            if not grouped_totals:
                if ignored_totals:
                    ignored_names = ', '.join(
                        escape(name)
                        for name in self.env['account.analytic.account'].browse(
                            list(ignored_totals.keys())
                        ).mapped('display_name')
                    )
                    req.monthly_budget_check_result = _(
                        '<div class="alert alert-info">%s</div>'
                    ) % format_ignored_analytic_accounts_message(ignored_names)
                else:
                    req.monthly_budget_check_result = _(
                        '<div class="alert alert-info">'
                        '%s'
                        '</div>'
                    ) % format_no_analytic_distribution_message()
                req.budget_warning = False
                continue

            html_parts = []
            has_warning = False
            AnalyticAccount = self.env['account.analytic.account']
            BudgetLine = self.env['monthly.budget.line']
            for plan, plan_totals in grouped_totals:
                for account_id, pr_amt in plan_totals.items():
                    analytic = AnalyticAccount.browse(account_id)
                    if not analytic.exists():
                        continue
                    budget_line = BudgetLine._find_budget_line(plan, {'analytic_account_id': account_id}, log_fallback=False)
                    if not budget_line:
                        html_parts.append(
                            '<div class="alert alert-warning">%s</div>'
                            % format_missing_budget_line_message(analytic.name, plan.name)
                        )
                        continue
                    budget_line = budget_line[0]
                    active_commitment = self.env['budget.commitment'].sudo().search([
                        ('document_model', '=', self._name),
                        ('document_id', '=', req.id),
                        ('analytic_account_id', '=', account_id),
                        ('budget_source', '=', 'monthly'),
                        ('state', 'in', ('reserved', 'used')),
                    ], limit=1)
                    already_committed = budget_line.reserved_amount + budget_line.used_amount
                    total_after = already_committed if active_commitment else already_committed + pr_amt
                    remaining = budget_line.budget_amount - total_after
                    is_over = remaining < 0
                    if is_over:
                        has_warning = True
                    status_class = 'danger' if is_over else 'success'
                    status_icon = '&#10060;' if is_over else '&#9989;'
                    html_parts.append(
                        '<div class="card mb-2 border-%s">'
                        '<div class="card-body p-2">'
                        '<h6 class="card-title">%s %s <small class="text-muted">(%s)</small></h6>'
                        '<table class="table table-sm table-borderless mb-0">'
                        '<tr><td>%s</td><td class="text-end">%s</td></tr>'
                        '<tr><td>%s</td><td class="text-end">%s</td></tr>'
                        '<tr><td>%s</td><td class="text-end">%s</td></tr>'
                        '<tr class="border-top"><td><strong>%s</strong></td>'
                        '<td class="text-end text-%s"><strong>%s %s</strong></td></tr>'
                        '</table></div></div>' % (
                            status_class, status_icon, analytic.name, escape(plan.name),
                            _('Monthly Budget'), '{:,.2f}'.format(budget_line.budget_amount),
                            _('Reserved + Used'), '{:,.2f}'.format(already_committed),
                            _('This PR'), '{:,.2f}'.format(pr_amt),
                            _('Remaining After'), status_class,
                            '{:,.2f}'.format(remaining),
                            _('OK') if not is_over else _('Exceeded!'),
                        )
                    )
            req.monthly_budget_check_result = ''.join(html_parts)
            req.budget_warning = has_warning

    def action_check_monthly_budget(self):
        """Button action to trigger monthly budget check recomputation."""
        self.ensure_one()
        self._compute_monthly_budget_check()
        return True

    def action_request_monthly_budget_approval(self):
        """Submit a monthly budget approval request when budget is exceeded."""
        self.ensure_one()
        target_date = self.payment_date
        analytic_totals = {}
        for line in self.requisition_order_ids:
            for account_id, amount in extract_analytic_amounts(line):
                analytic_totals[account_id] = analytic_totals.get(account_id, 0.0) + amount

        grouped_totals, _ignored_totals = split_analytic_totals_by_plan(
            self.env, target_date, self.company_id.id, analytic_totals,
        )
        if not grouped_totals:
            return

        # Document Amount = actual PR total (sum of all line subtotals)
        pr_amount = sum(self.requisition_order_ids.mapped('price_subtotal'))
        # Analytic Amount = sum of allocated amounts across budget plans
        analytic_amount = sum(analytic_totals.values())
        
        limit_amt = 0.0
        used = 0.0
        reserved = 0.0
        AnalyticAccount = self.env['account.analytic.account']
        BudgetLine = self.env['monthly.budget.line']
        budget_line_names = []
        
        for plan, plan_totals in grouped_totals:
            for account_id, amt in plan_totals.items():
                analytic = AnalyticAccount.browse(account_id)
                if not analytic.exists():
                    continue
                bl = BudgetLine._find_budget_line(plan, {'analytic_account_id': account_id}, log_fallback=False)
                if bl:
                    limit_amt += bl.budget_amount
                    used += bl.used_amount
                    reserved += bl.reserved_amount
                    budget_line_names.append('%s (%s)' % (bl.analytic_account_id.name, plan.name))
                
        overage = max(0.0, used + reserved + analytic_amount - limit_amt)
        primary_plan = get_first_plan_from_groups(grouped_totals)

        return {
            'name': _('Request Monthly Budget Approval'),
            'type': 'ir.actions.act_window',
            'res_model': 'monthly.budget.request.reason.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_document_type': 'pr',
                'default_ref_id': self.id,
                'default_budget_line_names': ', '.join(budget_line_names),
                'default_amount_requested': pr_amount,
                'default_amount_analytic': analytic_amount,
                'default_amount_used': used,
                'default_amount_reserved': reserved,
                'default_amount_limit': limit_amt,
                'default_amount_overage': overage,
                'default_plan_id': primary_plan.id if primary_plan else False,
            }
        }

    # ── Recompute Approval Request on document change ────────────

    def _recompute_budget_approval_request(self):
        """Recompute amounts on existing pending/approved budget approval requests
        when the PR is modified (lines changed, amounts changed, etc.)."""
        self.ensure_one()
        ApprovalReq = self.env['buz.monthly.budget.approval.request'].sudo()
        requests = ApprovalReq.search([
            ('document_type', '=', 'pr'),
            ('ref_pr_id', '=', self.id),
            ('state', 'in', ('pending', 'approved')),
        ])
        if not requests:
            return

        target_date = self.payment_date
        if not target_date:
            return

        analytic_totals = {}
        for line in self.requisition_order_ids:
            for account_id, amount in extract_analytic_amounts(line):
                analytic_totals[account_id] = analytic_totals.get(account_id, 0.0) + amount

        grouped_totals, _ignored_totals = split_analytic_totals_by_plan(
            self.env, target_date, self.company_id.id, analytic_totals,
        )
        if not grouped_totals:
            return

        pr_amount = sum(self.requisition_order_ids.mapped('price_subtotal'))
        analytic_amount = sum(analytic_totals.values())

        limit_amt = 0.0
        used = 0.0
        reserved = 0.0
        budget_line_names = []
        BudgetLine = self.env['monthly.budget.line']
        AnalyticAccount = self.env['account.analytic.account']

        for plan, plan_totals in grouped_totals:
            for account_id, amt in plan_totals.items():
                analytic = AnalyticAccount.browse(account_id)
                if not analytic.exists():
                    continue
                bl = BudgetLine._find_budget_line(plan, {'analytic_account_id': account_id}, log_fallback=False)
                if bl:
                    limit_amt += bl.budget_amount
                    used += bl.used_amount
                    reserved += bl.reserved_amount
                    budget_line_names.append('%s (%s)' % (bl.analytic_account_id.name, plan.name))

        overage = max(0.0, used + reserved + analytic_amount - limit_amt)
        primary_plan = get_first_plan_from_groups(grouped_totals)

        for req in requests:
            req.write({
                'amount_requested': pr_amount,
                'amount_analytic': analytic_amount,
                'amount_used': used,
                'amount_reserved': reserved,
                'amount_limit': limit_amt,
                'amount_overage': overage,
                'budget_line_name': ', '.join(budget_line_names) or req.budget_line_name,
                'plan_id': primary_plan.id if primary_plan else req.plan_id.id,
            })

        # Refresh only affected plans (case-by-case, skip MV for speed)
        affected_plans = set()
        for plan, _plan_totals in grouped_totals:
            affected_plans.add(plan.id)
        if affected_plans:
            for plan in self.env['monthly.budget.plan'].browse(list(affected_plans)):
                plan._refresh_budget_snapshot(refresh_report=False)

    # ── Budget enforcement ───────────────────────────────────────

    def action_confirm_requisition(self):
        """Override: check monthly analytic budget upon PR submission."""
        for req in self:
            req._check_monthly_analytic_budget()
        return super().action_confirm_requisition()

    def action_head_approval(self):
        """Override: check budget on head approval."""
        for req in self:
            req._check_monthly_analytic_budget()
        return super().action_head_approval()

    def action_purchase_approval(self):
        """Override: check budget on purchase approval."""
        for req in self:
            req._check_monthly_analytic_budget()
        return super().action_purchase_approval()

    def write(self, vals):
        prev_states = {rec.id: rec.state for rec in self}
        result = super().write(vals)
        if 'state' in vals:
            for rec in self:
                if rec.state in RESERVED_PR_STATES and prev_states.get(rec.id) != rec.state:
                    rec._reserve_monthly_analytic_budget()
        # Sync expected payment to linked POs (and cascade to Bills via PO)
        if 'payment_date' in vals and not self.env.context.get('skip_expected_payment_sync'):
            for rec in self:
                rec._sync_payment_date_to_linked_documents()
        # Recompute existing approval requests when PR lines or amounts change
        _approval_trigger_fields = {
            'requisition_order_ids', 'payment_date', 'payment_date_manual',
        }
        if _approval_trigger_fields & set(vals.keys()) and not self.env.context.get('skip_approval_recompute'):
            for rec in self:
                rec._recompute_budget_approval_request()
        return result

    def _sync_payment_date_to_linked_documents(self):
        """Sync PR expected payment date to linked POs, which then cascade to Bills."""
        self.ensure_one()
        PurchaseOrder = self.env['purchase.order'].sudo()
        # Find POs that originated from this PR
        linked_pos = PurchaseOrder.search([
            ('company_id', '=', self.company_id.id),
            '|', '|',
            ('requisition_order', '=', self.name),
            ('pr_number', '=', self.name),
            ('origin', '=', self.name),
        ])
        for po in linked_pos:
            po.with_context(skip_expected_payment_sync=True).write({
                'payment_date': self.payment_date,
                'payment_date_manual': self.payment_date,
            })
            # PO.write will trigger _sync_linked_vendor_bills via its own write()
            # but since we use skip_expected_payment_sync, we call it explicitly
            po._sync_linked_vendor_bills()
            # Refresh budget reservations for the PO
            po._reserve_monthly_budget_for_direct_rfq()
            if po.state in ('purchase', 'done'):
                po._consume_monthly_analytic_budget()

    def _check_monthly_analytic_budget(self):
        """Verify each PR line's analytic distribution has sufficient monthly budget."""
        self.ensure_one()
        target_date = self.payment_date
        if not target_date or not self.requisition_order_ids:
            return

        # Check if an approved budget request exists
        approved = self.env['buz.monthly.budget.approval.request'].sudo().search([
            ('document_type', '=', 'pr'),
            ('ref_pr_id', '=', self.id),
            ('state', '=', 'approved'),
        ], limit=1)
        if approved:
            return  # Bypass budget check – approved

        analytic_totals = {}
        for line in self.requisition_order_ids:
            for account_id, amount in extract_analytic_amounts(line):
                analytic_totals[account_id] = analytic_totals.get(account_id, 0.0) + amount

        grouped_totals, ignored_totals = split_analytic_totals_by_plan(
            self.env, target_date, self.company_id.id, analytic_totals,
        )
        if not grouped_totals:
            if ignored_totals:
                ignored_names = ', '.join(
                    self.env['account.analytic.account'].browse(list(ignored_totals.keys())).mapped('display_name')
                )
                _logger.info('PR %s analytics ignored because they are not configured on an active plan: %s', self.name, ignored_names)
            raise UserError(_('ไม่พบแผนงบประมาณรายเดือน (Budget Plan) ที่รองรับสำหรับวันที่คาดว่าจะชำระเงินของเอกสารนี้'))

        AnalyticAccount = self.env['account.analytic.account']
        BudgetLine = self.env['monthly.budget.line']
        violations = []
        for plan, plan_totals in grouped_totals:
            for account_id, pr_amt in plan_totals.items():
                analytic = AnalyticAccount.browse(account_id)
                if not analytic.exists():
                    continue
                budget_line = BudgetLine._find_budget_line(plan, {'analytic_account_id': account_id})
                if not budget_line:
                    raise UserError(format_missing_budget_line_message(analytic.name, plan.name))

                budget_line = budget_line[:1] if len(budget_line) > 1 else budget_line
                total_committed = budget_line.reserved_amount + budget_line.used_amount
                active_commitment = self.env['budget.commitment'].sudo().search([
                    ('document_model', '=', self._name),
                    ('document_id', '=', self.id),
                    ('analytic_account_id', '=', account_id),
                    ('budget_source', '=', 'monthly'),
                    ('state', 'in', ('reserved', 'used')),
                ], limit=1)

                if not active_commitment:
                    total_committed += pr_amt

                overage = total_committed - budget_line.budget_amount

                if overage > 0:
                    violations.append({
                        'analytic': '%s (%s)' % (analytic.name, plan.name),
                        'budget': budget_line.budget_amount,
                        'committed': total_committed,
                        'pr_amt': pr_amt,
                        'overage': overage,
                    })

        if violations:
            msg_lines = [_('Monthly Analytic Budget Exceeded!\n')]
            for v in violations:
                msg_lines.append(_(
                    'Analytic: %s\n'
                    '  Budget: %s | Committed: %s | This PR: %s | Over by: %s\n'
                ) % (
                    v['analytic'],
                    '{:,.2f}'.format(v['budget']),
                    '{:,.2f}'.format(v['committed']),
                    '{:,.2f}'.format(v['pr_amt']),
                    '{:,.2f}'.format(v['overage']),
                ))
            
            msg_lines.append(_('\nPlease click "Request Budget Approval" button to submit an approval request.'))
            raise UserError('\n'.join(msg_lines))

    def _reserve_monthly_analytic_budget(self):
        """
        Reserve monthly analytic budget for this PR.

        Flow (concurrency-safe):
        1. Determine analytic IDs from PR lines.
        2. Acquire FOR UPDATE row-level lock on matching budget lines.
        3. Re-read fresh budget data AFTER lock.
        4. Check for existing reservation (idempotency).
        5. Create commitment audit record.
        """
        self.ensure_one()
        target_date = self.payment_date
        if not target_date or not self.requisition_order_ids:
            return

        BudgetLine = self.env['monthly.budget.line']
        engine = self.env['budget.engine'].sudo()
        AnalyticAccount = self.env['account.analytic.account']

        analytic_totals = {}
        for line in self.requisition_order_ids:
            for account_id, amount in extract_analytic_amounts(line, BudgetLine):
                analytic_totals[account_id] = analytic_totals.get(account_id, 0.0) + amount

        grouped_totals, _ignored_totals = split_analytic_totals_by_plan(
            self.env, target_date, self.company_id.id, analytic_totals,
        )
        if not grouped_totals:
            return

        for plan, plan_totals in grouped_totals:
            BudgetLine._lock_budget_lines(list(plan_totals.keys()), plan.id)
            plan._refresh_budget_snapshot(refresh_report=False)

            for account_id, total_amt in plan_totals.items():
                analytic = AnalyticAccount.browse(account_id)
                if not analytic.exists() or not total_amt:
                    continue

                budget_line = BudgetLine._find_budget_line(plan, {'analytic_account_id': account_id})
                if not budget_line:
                    continue

                commitments = self.env['budget.commitment'].sudo().search([
                    ('document_model', '=', self._name),
                    ('document_id', '=', self.id),
                    ('analytic_account_id', '=', account_id),
                    ('budget_source', '=', 'monthly'),
                    ('state', '=', 'reserved'),
                ])
                note = _('Reserved from PR %s - %s') % (self.name, analytic.name)

                if commitments:
                    commitment = commitments[0]
                    if commitment.amount != total_amt or commitment.date != target_date:
                        commitment.write({'amount': total_amt, 'date': target_date, 'note': note})
                    if len(commitments) > 1:
                        commitments[1:].action_release()
                else:
                    engine.reserve_budget({
                        'budget_source': 'monthly',
                        'document_model': self._name,
                        'document_id': self.id,
                        'amount': total_amt,
                        'date': target_date,
                        'company_id': self.company_id.id,
                        'analytic_account_id': account_id,
                        'note': note,
                    })
                _logger.info(
                    'Monthly budget reserved: PR=%s analytic=%s amount=%.4f plan=%s',
                    self.name, analytic.name, total_amt, plan.name,
                )

            plan._refresh_budget_snapshot(refresh_report=True)

    def action_head_cancel(self):
        """Release monthly budget reservations when head cancels PR."""
        result = super().action_head_cancel()
        for req in self:
            req._release_monthly_analytic_budget()
        return result

    def action_purchase_cancel(self):
        """Release monthly budget reservations when purchase cancels PR."""
        result = super().action_purchase_cancel()
        for req in self:
            req._release_monthly_analytic_budget()
        return result

    def action_cancel_requisition(self):
        """Release monthly budget reservations when requester cancels PR."""
        result = super().action_cancel_requisition()
        for req in self:
            req._release_monthly_analytic_budget()
        return result

    def _release_monthly_analytic_budget(self):
        """Release previously reserved monthly budget amounts."""
        self.ensure_one()
        engine = self.env['budget.engine'].sudo()
        document_model = self._name
        document_id = self.id
        # Release all commitment records for this document
        engine.release_budget({
            'budget_source': 'monthly',
            'document_model': document_model,
            'document_id': document_id,
            'amount': 0,
            'company_id': self.company_id.id,
        })

        for plan in find_active_monthly_plans(self.env, self.payment_date, self.company_id.id):
            plan._refresh_budget_snapshot(refresh_report=True)


class RequisitionOrderMonthly(models.Model):
    _inherit = 'requisition.order'

    @api.onchange('partner_id')
    def _onchange_partner_id_refresh_requisition_payment_date(self):
        for line in self:
            requisition = line.requisition_product_id
            if not requisition or requisition.payment_date_manual:
                continue
            requisition.payment_date = requisition._get_auto_payment_date()
