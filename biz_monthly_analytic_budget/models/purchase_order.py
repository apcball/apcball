# -*- coding: utf-8 -*-
import logging
from datetime import timedelta
from decimal import Decimal
from markupsafe import escape
from odoo import api, fields, models, _
from odoo.exceptions import UserError

from .budget_utils import (
    RESERVED_PR_STATES,
    extract_analytic_amounts,
    filter_analytic_totals_for_plan,
    find_active_monthly_plan,
    format_ignored_analytic_accounts_message,
    format_missing_budget_line_message,
    format_no_analytic_distribution_message,
)

_logger = logging.getLogger(__name__)

# Keep backward compatibility alias
_extract_po_line_analytic_amounts = extract_analytic_amounts


class PurchaseOrder(models.Model):
    """Extend purchase.order to consume monthly analytic budget on confirmation."""
    _inherit = 'purchase.order'

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

    def _compute_is_budget_reserved(self):
        Commitment = self.env['budget.commitment'].sudo()
        for order in self:
            has_commitment = False
            
            if order.state in ('purchase', 'done'):
                has_commitment = bool(Commitment.search([
                    ('document_model', '=', order._name),
                    ('document_id', '=', order.id),
                    ('state', 'in', ('reserved', 'used')),
                    ('budget_source', '=', 'monthly')
                ], limit=1))
                
            if not has_commitment:
                source_id = order._get_source_requisition_id()
                if source_id and source_id != order.id:
                    has_commitment = bool(Commitment.search([
                        ('document_model', '=', 'employee.purchase.requisition'),
                        ('document_id', '=', source_id),
                        ('state', 'in', ('reserved', 'used')),
                        ('budget_source', '=', 'monthly')
                    ], limit=1))
                    
            order.is_budget_reserved = has_commitment

    def _compute_budget_approval_id(self):
        ApprovalReq = self.env['buz.monthly.budget.approval.request'].sudo()
        for rec in self:
            req = ApprovalReq.search([
                ('document_type', '=', 'po'),
                ('ref_po_id', '=', rec.id),
            ], limit=1, order='id desc')
            
            if not req and hasattr(rec, 'requisition_order') and rec.requisition_order:
                pr = self.env['employee.purchase.requisition'].sudo().search([('name', '=', rec.requisition_order)], limit=1)
                if pr:
                    req = ApprovalReq.search([
                        ('document_type', '=', 'pr'),
                        ('ref_pr_id', '=', pr.id),
                    ], limit=1, order='id desc')
                    
            rec.buz_budget_approval_id = req

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        orders._reserve_monthly_budget_for_direct_rfq()
        return orders

    @api.depends('date_order', 'partner_id', 'partner_id.property_supplier_payment_term_id')
    def _compute_payment_date(self):
        for order in self:
            if order.payment_date_manual:
                order.payment_date = order.payment_date_manual
                continue
            
            # Priority logic:
            # 2. Vendor payment term
            payment_term = order.partner_id.property_supplier_payment_term_id
            if payment_term:
                p_date = order.date_order or fields.Date.today()
                # Check method availability directly to avoid exception overhead
                if hasattr(payment_term, 'compute'):
                    res = payment_term.compute(value=1, date_ref=p_date)
                    if res and res[0] and res[0][0]:
                        order.payment_date = res[0][0]
                        continue
                elif hasattr(payment_term, '_compute_terms'):
                    try:
                        res = payment_term._compute_terms(
                            date_ref=p_date,
                            currency=order.company_id.currency_id,
                            company=order.company_id,
                            taxes_and_subtotals=[{'name': '', 'tax_amount': 0.0, 'base_amount': 1.0}],
                            untaxed_amount=1.0,
                            empty_taxes=True,
                            sign=1
                        )
                        if res and getattr(res, 'get', None) and res.get('line_ids'):
                            # Odoo 17 returns a dict containing line_ids list
                            lines = res.get('line_ids')
                            order.payment_date = lines[-1].get('date') if lines else p_date
                            continue
                        elif res and isinstance(res, list):
                            # Other versions might return list of dicts directly
                            order.payment_date = res[-1].get('date') if res else p_date
                            continue
                    except Exception as e:
                        _logger.warning("biz_monthly_analytic_budget _compute_terms failed: %s", e)
                        
                # Ultimate fallback: manual parsing of days
                max_days = 0
                for line in payment_term.line_ids:
                    days = getattr(line, 'days', getattr(line, 'nb_days', 0))
                    months = getattr(line, 'months', 0)
                    total_days = (months * 30) + days
                    if total_days > max_days:
                        max_days = total_days
                if max_days > 0:
                    order.payment_date = p_date + timedelta(days=max_days)
                    continue

            # Final fallback: no vendor payment term, use date_order + 30 days
            order.payment_date = (order.date_order or fields.Date.today()) + timedelta(days=30)

    def _inverse_payment_date(self):
        for order in self:
            order.payment_date_manual = order.payment_date

    def write(self, vals):
        result = super().write(vals)
        if any(key in vals for key in ('state', 'payment_date', 'payment_date_manual', 'order_line', 'partner_id')):
            self._reserve_monthly_budget_for_direct_rfq()
        if any(key in vals for key in ('payment_date', 'payment_date_manual', 'partner_id', 'order_line')):
            self._sync_linked_vendor_bills()
            for order in self:
                if order.state in ('purchase', 'done'):
                    order._consume_monthly_analytic_budget()
        return result

    def _sync_linked_vendor_bills(self):
        """Refresh linked vendor bills when the PO expected payment changes."""
        AccountMove = self.env['account.move'].sudo()
        for order in self:
            bills = AccountMove.search([
                ('move_type', 'in', ('in_invoice', 'in_refund')),
                ('company_id', '=', order.company_id.id),
                '|',
                ('purchase_id', '=', order.id),
                ('invoice_origin', '=', order.name),
            ])
            if not bills and hasattr(order, 'requisition_order') and order.requisition_order:
                bills = AccountMove.search([
                    ('move_type', 'in', ('in_invoice', 'in_refund')),
                    ('company_id', '=', order.company_id.id),
                    ('invoice_origin', '=', order.requisition_order),
                ])
            for bill in bills:
                if bill._get_related_purchase_order() != order:
                    continue
                bill._sync_monthly_bill_budget()

    @api.depends('order_line.price_subtotal', 'order_line.analytic_distribution', 'payment_date')
    def _compute_monthly_budget_check(self):
        for order in self:
            target_date = order.payment_date
            if not target_date or not order.order_line:
                order.monthly_budget_check_result = ''
                order.budget_warning = False
                continue

            plan = find_active_monthly_plan(self.env, target_date, order.company_id.id)
            if not plan:
                order.monthly_budget_check_result = _(
                    '<div class="alert alert-info">'
                    'No active monthly analytic budget plan found for the expected payment date.'
                    '</div>'
                )
                order.budget_warning = False
                continue

            analytic_totals = {}
            for line in order.order_line:
                for account_id, amount in extract_analytic_amounts(line):
                    analytic_totals[account_id] = analytic_totals.get(account_id, 0.0) + amount

            analytic_totals, ignored_totals = filter_analytic_totals_for_plan(plan, analytic_totals)

            if not analytic_totals:
                if ignored_totals:
                    ignored_names = ', '.join(
                        escape(name)
                        for name in self.env['account.analytic.account'].browse(
                            list(ignored_totals.keys())
                        ).mapped('display_name')
                    )
                    order.monthly_budget_check_result = _(
                        '<div class="alert alert-info">%s</div>'
                    ) % format_ignored_analytic_accounts_message(ignored_names)
                else:
                    order.monthly_budget_check_result = _(
                        '<div class="alert alert-info">'
                        '%s'
                        '</div>'
                    ) % format_no_analytic_distribution_message()
                order.budget_warning = False
                continue

            html_parts = []
            has_warning = False
            AnalyticAccount = self.env['account.analytic.account']
            BudgetLine = self.env['monthly.budget.line']
            has_pr = order._has_active_source_requisition_for_plan(plan)
            
            if has_pr:
                order.monthly_budget_check_result = _(
                    '<div class="alert alert-success">'
                    '<strong>Budget Covered by PR:</strong> งบประมาณถูกจองและตรวจสอบผ่าน PR ต้นทางเรียบร้อยแล้ว'
                    '</div>'
                )
                order.budget_warning = False
                continue
                
            for account_id, po_amt in analytic_totals.items():
                analytic = AnalyticAccount.browse(account_id)
                if not analytic.exists():
                    continue
                dims = {'analytic_account_id': account_id}
                budget_line = BudgetLine._find_budget_line(plan, dims, log_fallback=False)
                if not budget_line:
                    html_parts.append(
                        '<div class="alert alert-warning">%s</div>'
                        % format_missing_budget_line_message(analytic.name, plan.name)
                    )
                    continue
                budget_line = budget_line[0]
                
                # Check if this PO is already reserved
                total_committed = budget_line.reserved_amount + budget_line.used_amount
                if not has_pr and not order._is_counted_in_monthly_budget_reserve(plan):
                    # New/uncounted direct PO: add it for preview.
                    total_committed += po_amt
                
                remaining = budget_line.budget_amount - total_committed
                is_over = remaining < 0
                if is_over:
                    has_warning = True
                status_class = 'danger' if is_over else 'success'
                status_icon = '&#10060;' if is_over else '&#9989;'
                
                html_parts.append(
                    '<div class="card mb-2 border-%s">'
                    '<div class="card-body p-2">'
                    '<h6 class="card-title">%s %s</h6>'
                    '<table class="table table-sm table-borderless mb-0">'
                    '<tr><td>%s</td><td class="text-end">%s</td></tr>'
                    '<tr><td>%s</td><td class="text-end">%s</td></tr>'
                    '<tr><td>%s</td><td class="text-end">%s</td></tr>'
                    '<tr class="border-top"><td><strong>%s</strong></td>'
                    '<td class="text-end text-%s"><strong>%s %s</strong></td></tr>'
                    '</table></div></div>' % (
                        status_class, status_icon, analytic.name,
                        _('Monthly Budget'), '{:,.2f}'.format(budget_line.budget_amount),
                        _('Reserved + Used'), '{:,.2f}'.format(budget_line.reserved_amount + budget_line.used_amount),
                        _('This PO'), '{:,.2f}'.format(po_amt),
                        _('Remaining After'), status_class,
                        '{:,.2f}'.format(remaining),
                        _('OK') if not is_over else _('Exceeded!'),
                    )
                )
            order.monthly_budget_check_result = ''.join(html_parts)
            order.budget_warning = has_warning

    def _reserve_monthly_budget_for_direct_rfq(self):
        """Reserve monthly budget immediately for direct RFQs / POs without a PR."""
        BudgetLine = self.env['monthly.budget.line']
        engine = self.env['budget.engine']
        AnalyticAccount = self.env['account.analytic.account']
        for order in self:
            target_date = order.payment_date
            if not target_date:
                continue
            plan = find_active_monthly_plan(self.env, target_date, order.company_id.id)
            if not plan:
                continue
            if order._has_active_source_requisition_for_plan(plan):
                continue
            # Only reserve while the PO is still before confirmation.
            if order.state not in ('draft', 'sent', 'to approve'):
                continue
            analytic_totals = {}
            for line in order.order_line:
                for account_id, amount in extract_analytic_amounts(line, BudgetLine):
                    analytic_totals[account_id] = analytic_totals.get(account_id, 0.0) + amount

            analytic_totals, _ignored_totals = filter_analytic_totals_for_plan(plan, analytic_totals)
            if not analytic_totals:
                continue

            BudgetLine._lock_budget_lines(list(analytic_totals.keys()), plan.id)
            plan._refresh_budget_snapshot(refresh_report=False)

            for account_id, amount in analytic_totals.items():
                if not amount:
                    continue
                analytic = AnalyticAccount.browse(account_id)
                if not analytic.exists():
                    continue
                if not BudgetLine._find_budget_line(plan, {'analytic_account_id': account_id}, log_fallback=False):
                    continue

                existing = self.env['budget.commitment'].sudo().search([
                    ('document_model', '=', order._name),
                    ('document_id', '=', order.id),
                    ('analytic_account_id', '=', account_id),
                    ('budget_source', '=', 'monthly'),
                    ('state', '=', 'reserved'),
                ], limit=1)
                if existing:
                    if existing.amount != amount or existing.date != target_date:
                        existing.write({
                            'amount': amount,
                            'date': target_date,
                            'note': _('Reserved from PO %s - %s') % (order.name, analytic.name),
                        })
                    continue

                engine.reserve_budget({
                    'budget_source': 'monthly',
                    'document_model': order._name,
                    'document_id': order.id,
                    'amount': amount,
                    'date': target_date,
                    'company_id': order.company_id.id,
                    'analytic_account_id': account_id,
                    'note': _('Reserved from PO %s - %s') % (order.name, analytic.name),
                })

            plan._refresh_budget_snapshot(refresh_report=True)

    def action_check_monthly_budget(self):
        """Button action to trigger monthly budget check recomputation."""
        self.ensure_one()
        self._compute_monthly_budget_check()
        return True

    def action_request_monthly_budget_approval(self):
        """Submit a monthly budget approval request when budget is exceeded."""
        self.ensure_one()
        target_date = self.payment_date
        plan = find_active_monthly_plan(self.env, target_date, self.company_id.id)
        if not plan:
            return

        analytic_totals = {}
        for line in self.order_line:
            for account_id, amount in extract_analytic_amounts(line):
                analytic_totals[account_id] = analytic_totals.get(account_id, 0.0) + amount

        analytic_totals, _ignored_totals = filter_analytic_totals_for_plan(plan, analytic_totals)

        if not analytic_totals:
            return

        po_amount = sum(analytic_totals.values())
        
        limit_amt = 0.0
        used = 0.0
        reserved = 0.0
        AnalyticAccount = self.env['account.analytic.account']
        BudgetLine = self.env['monthly.budget.line']
        budget_line_names = []
        has_pr = self._has_active_source_requisition_for_plan(plan)
        po_already_reserved = self._is_counted_in_monthly_budget_reserve(plan)
        
        for account_id, amt in analytic_totals.items():
            analytic = AnalyticAccount.browse(account_id)
            if not analytic.exists():
                continue
            dims = {'analytic_account_id': account_id}
            bl = BudgetLine._find_budget_line(plan, dims, log_fallback=False)
            if bl:
                limit_amt += bl.budget_amount
                used += bl.used_amount
                
                # if this is a direct PO, it hasn't reserved anything yet, 
                # so we need to add its amount to overage calculation
                if not has_pr and not po_already_reserved:
                    reserved += bl.reserved_amount + po_amount
                else:
                    reserved += bl.reserved_amount
                budget_line_names.append(bl.analytic_account_id.name)
                
        overage = max(0.0, used + reserved - limit_amt)

        return {
            'name': _('Request Monthly Budget Approval'),
            'type': 'ir.actions.act_window',
            'res_model': 'monthly.budget.request.reason.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_document_type': 'po',
                'default_ref_id': self.id,
                'default_budget_line_names': ', '.join(budget_line_names),
                'default_amount_requested': po_amount,
                'default_amount_used': used,
                'default_amount_reserved': reserved,
                'default_amount_limit': limit_amt,
                'default_amount_overage': overage,
                'default_plan_id': plan.id,
            }
        }

    def button_confirm(self):
        """On PO confirmation: consume monthly analytic budget reservations."""
        # Check budget before confirmation
        for order in self:
            order._check_monthly_analytic_budget_limit()
        result = super().button_confirm()
        for order in self:
            order._consume_monthly_analytic_budget()
        # Refresh materialized view after budget consumption
        try:
            self.env['monthly.budget.report'].refresh_materialized_view()
        except Exception as e:
            _logger.warning('Could not refresh monthly_budget_report MV after PO confirm: %s', e)
        return result

    def action_submit_for_review(self):
        """Check budget before submitting for review."""
        for order in self:
            order._check_monthly_analytic_budget_limit()
        if hasattr(super(), 'action_submit_for_review'):
            return super().action_submit_for_review()
        return True

    def _check_monthly_analytic_budget_limit(self):
        """Verify budget before PO confirmation or submission."""
        self.ensure_one()
        ApprovalReq = self.env['buz.monthly.budget.approval.request'].sudo()

        # 1. Check if an approved budget request exists for THIS PO
        approved_po = ApprovalReq.search([
            ('document_type', '=', 'po'),
            ('ref_po_id', '=', self.id),
            ('state', '=', 'approved'),
        ], limit=1)
        if approved_po:
            return  # Bypass

        # 2. BYPASS budget check entirely if the PO is linked to a PR
        source_id = self._get_source_requisition_id()
        if source_id and source_id != self.id:
            return

        target_date = self.payment_date
        if not target_date:
            return

        plan = find_active_monthly_plan(self.env, target_date, self.company_id.id)
        if not plan:
            raise UserError(_('ไม่พบแผนงบประมาณรายเดือน (Budget Plan) ที่รองรับสำหรับวันที่คาดว่าจะชำระเงินของเอกสารนี้'))

        analytic_totals = {}
        for line in self.order_line:
            for account_id, amount in extract_analytic_amounts(line):
                analytic_totals[account_id] = analytic_totals.get(account_id, 0.0) + amount

        analytic_totals, _ignored_totals = filter_analytic_totals_for_plan(plan, analytic_totals)

        AnalyticAccount = self.env['account.analytic.account']
        BudgetLine = self.env['monthly.budget.line']
        violations = []
        for account_id, po_amt in analytic_totals.items():
            analytic = AnalyticAccount.browse(account_id)
            if not analytic.exists():
                continue
            dims = {'analytic_account_id': account_id}
            budget_line = BudgetLine._find_budget_line(plan, dims)
            if not budget_line:
                raise UserError(format_missing_budget_line_message(analytic.name, plan.name))

            budget_line = budget_line[:1] or budget_line
            
            # total_committed = already used + already reserved
            total_committed = budget_line.reserved_amount + budget_line.used_amount
            
            # If it's a direct PO (no PR), it hasn't reserved anything yet, so we must add po_amt.
            # If it came from a PR, the PR already reserved it, so it's already in total_committed.
            # However, if the PO amount is higher than what was reserved by PR, we should check that too.
            # For simplicity, if it's a direct PO, we add it. 
            # If it's from PR, we assume it's already in reserved_amount.
            
            has_pr = self._has_active_source_requisition_for_plan(plan)
            if not has_pr and not self._is_counted_in_monthly_budget_reserve(plan):
                total_committed += po_amt
            
            if total_committed > budget_line.budget_amount:
                violations.append({
                    'analytic': analytic.name,
                    'budget': budget_line.budget_amount,
                    'committed': total_committed,
                    'overage': total_committed - budget_line.budget_amount,
                })

        if violations:
            msg_lines = [_('Monthly Analytic Budget Exceeded!\n')]
            for v in violations:
                msg_lines.append(_(
                    'Analytic: %s\n'
                    '  Budget: %s | Committed: %s | Over by: %s\n'
                ) % (
                    v['analytic'],
                    '{:,.2f}'.format(v['budget']),
                    '{:,.2f}'.format(v['committed']),
                    '{:,.2f}'.format(v['overage']),
                ))
            
            msg_lines.append(_('\nPlease click "Request Budget Approval" button to submit an approval request.'))
            raise UserError('\n'.join(msg_lines))

    def _consume_monthly_analytic_budget(self):
        """
        Convert monthly analytic budget reservations to 'used' state.
        Called after PO is confirmed.

        Flow (concurrency-safe):
        1. Determine analytic IDs from PO lines.
        2. Acquire FOR UPDATE row-level lock on matching budget lines.
        3. Re-read fresh data AFTER lock.
        4. Create/update commitment audit records.
        """
        self.ensure_one()
        BudgetLine = self.env['monthly.budget.line']
        engine = self.env['budget.engine']
        AnalyticAccount = self.env['account.analytic.account']

        target_date = self.payment_date
        if not target_date:
            return

        plan = find_active_monthly_plan(self.env, target_date, self.company_id.id)
        if not plan:
            return

        # Aggregate UNBILLED amounts by analytic across all PO lines
        analytic_totals = {}
        for line in self.order_line:
            # Find billed qty including draft and posted bills (excluding cancelled)
            invoice_lines = line.invoice_lines.filtered(lambda l: l.move_id.state != 'cancel')
            billed_qty = sum(invoice_lines.mapped('quantity'))
            
            # Unbilled qty cannot be negative
            unbilled_qty = max(0.0, line.product_qty - billed_qty)
            ratio = (unbilled_qty / line.product_qty) if line.product_qty else 0.0
            
            for account_id, amount in extract_analytic_amounts(line, BudgetLine):
                unbilled_amount = amount * ratio
                if unbilled_amount > 0:
                    analytic_totals[account_id] = analytic_totals.get(account_id, 0.0) + unbilled_amount

        # If everything is fully billed, we should still proceed with analytic_totals = {account_id: 0}
        # to release the remaining PO commitments.
        if not analytic_totals:
            # Gather all accounts that were originally on this PO so we can zero them out
            for line in self.order_line:
                for account_id, amount in extract_analytic_amounts(line, BudgetLine):
                    if account_id not in analytic_totals:
                        analytic_totals[account_id] = 0.0

        analytic_totals, _ignored_totals = filter_analytic_totals_for_plan(plan, analytic_totals)

        # --- Concurrency: acquire row-level lock BEFORE reading budget values ---
        BudgetLine._lock_budget_lines(list(analytic_totals.keys()), plan.id)

        # Re-read the current snapshot AFTER acquiring the lock
        plan._refresh_budget_snapshot(refresh_report=False)

        for account_id, amount in analytic_totals.items():
            analytic = AnalyticAccount.browse(account_id)
            if not analytic.exists():
                continue
            dims = {'analytic_account_id': account_id}
            budget_line = BudgetLine._find_budget_line(plan, dims)
            if not budget_line:
                continue

            document_model, document_id = self._get_budget_document_identity()

            commitments = self.env['budget.commitment'].sudo().search([
                ('document_model', '=', document_model),
                ('document_id', '=', document_id),
                ('analytic_account_id', '=', account_id),
                ('budget_source', '=', 'monthly'),
                ('state', '=', 'reserved'),
            ])
            note = _('Reserved (Unbilled) by PO %s - %s') % (self.name, analytic.name)
            
            if commitments:
                commitment = commitments[0]
                if commitment.amount != amount or commitment.date != target_date:
                    commitment.write({'amount': amount, 'date': target_date, 'note': note})
                if len(commitments) > 1:
                    commitments[1:].action_release()
            else:
                engine.reserve_budget({
                    'budget_source': 'monthly',
                    'document_model': document_model,
                    'document_id': document_id,
                    'amount': amount,
                    'date': target_date,
                    'company_id': self.company_id.id,
                    'analytic_account_id': account_id,
                    'note': note,
                })
            
            # Also release any stale 'used' commitments on the PO itself, since PO is now 'reserved'
            stale_used = self.env['budget.commitment'].sudo().search([
                ('document_model', '=', document_model),
                ('document_id', '=', document_id),
                ('analytic_account_id', '=', account_id),
                ('budget_source', '=', 'monthly'),
                ('state', '=', 'used'),
            ])
            if stale_used:
                stale_used.action_release()

        plan._refresh_budget_snapshot(refresh_report=True)

    def _get_source_requisition(self):
        """Return the source employee PR linked to this PO, if any."""
        self.ensure_one()
        Requisition = self.env['employee.purchase.requisition'].sudo()
        for ref in (
            getattr(self, 'requisition_order', '') or '',
            getattr(self, 'pr_number', '') or '',
            self.origin or '',
        ):
            ref = ref.strip()
            if not ref:
                continue
            req = Requisition.search([('name', '=', ref)], limit=1)
            if req:
                return req
        return Requisition.browse()

    def _has_active_source_requisition_for_plan(self, plan):
        """True only when a linked PR is actually reserved by this monthly plan."""
        self.ensure_one()
        req = self._get_source_requisition()
        return bool(
            req
            and req.state in RESERVED_PR_STATES
            and req.payment_date
            and plan.date_from <= req.payment_date <= plan.date_to
            and req.company_id.id == plan.company_id.id
        )

    def _is_counted_in_monthly_budget_reserve(self, plan):
        """Return whether this PO should already be present in reserved_amount."""
        self.ensure_one()
        if self.state not in ('draft', 'sent', 'to approve', 'purchase', 'done'):
            return False
        po_date = self.payment_date or (self.date_order.date() if self.date_order else False)
        return bool(
            po_date
            and plan.date_from <= po_date <= plan.date_to
            and self.company_id.id == plan.company_id.id
        )

    def _get_source_requisition_id(self):
        """
        Try to find the source purchase requisition ID that originated this PO.
        Falls back to PO id if not found.
        """
        self.ensure_one()
        req = self._get_source_requisition()
        if req:
            return req.id
        return self.id

    def _get_budget_document_identity(self):
        """Return the document identity used by the budget engine."""
        self.ensure_one()
        source_id = self._get_source_requisition_id()
        if source_id != self.id:
            return 'employee.purchase.requisition', source_id
        return self._name, self.id

    def button_cancel(self):
        """On PO cancel: release any consumed monthly analytic budget amounts."""
        prev_states = {order.id: order.state for order in self}
        result = super().button_cancel()
        for order in self:
            prev_state = prev_states.get(order.id)
            if prev_state == 'purchase':
                order._release_monthly_analytic_budget_on_cancel()
            else:
                plan = find_active_monthly_plan(self.env, order.payment_date, order.company_id.id)
                if plan and not order._has_active_source_requisition_for_plan(plan) and prev_state in ('draft', 'sent', 'to approve'):
                    order._release_monthly_analytic_budget_on_cancel()
        # Refresh materialized view after budget release
        try:
            self.env['monthly.budget.report'].refresh_materialized_view()
        except Exception as e:
            _logger.warning('Could not refresh monthly_budget_report MV after PO cancel: %s', e)
        return result

    def action_force_cancel_po_with_pr(self):
        """Force cancel a PO and its linked PR, restoring budget. Requires received items to be returned."""
        for order in self:
            # Check if goods need to be returned
            if any(line.qty_received > 0 for line in order.order_line):
                raise UserError(_(
                    'ไม่สามารถยกเลิกใบสั่งซื้อ %s ได้\n'
                    'เนื่องจากมีการรับสินค้าเข้าคลังไปแล้วบางส่วนหรือทั้งหมด\n'
                    'กรุณาทำรายการส่งคืนสินค้า (Return) กลับไปยังผู้จัดจำหน่าย เพื่อให้ยอดรับสินค้า (Received) กลับมาเป็น 0 ก่อน จึงจะสามารถยกเลิกได้'
                ) % order.name)

            # Cancel unfinished pickings
            for pick in order.picking_ids.filtered(lambda p: p.state not in ['done', 'cancel']):
                try:
                    pick.action_cancel()
                except Exception:
                    pass

            # Forcefully set PO to cancel and release budget
            order.write({'state': 'cancel'})
            try:
                order._release_monthly_analytic_budget_on_cancel()
            except Exception:
                pass

            # Find and Cancel Linked PR
            if hasattr(order, 'requisition_order') and order.requisition_order:
                pr = self.env['employee.purchase.requisition'].sudo().search([
                    ('name', '=', order.requisition_order)
                ], limit=1)
                if pr and pr.state not in ['cancelled', 'cancel']:
                    pr.write({'state': 'cancelled'})
                    if hasattr(pr, '_release_monthly_analytic_budget'):
                        try:
                            pr._release_monthly_analytic_budget()
                        except Exception:
                            pass

    def _release_monthly_analytic_budget_on_cancel(self):
        """Re-open budget amounts when a confirmed PO is cancelled.

        Note: used_amount is a live computed field reading from posted invoices,
        so we don't need to manually adjust it. We only release the audit trail
        (budget.commitment records) via the budget engine.
        """
        self.ensure_one()
        engine = self.env['budget.engine']
        plan = find_active_monthly_plan(self.env, self.payment_date, self.company_id.id)

        document_model, document_id = self._get_budget_document_identity()

        # Mark related commitment records as released
        engine.release_budget({
            'budget_source': 'monthly',
            'document_model': document_model,
            'document_id': document_id,
            'amount': 0,
            'company_id': self.company_id.id,
        })

        if plan:
            plan._refresh_budget_snapshot(refresh_report=True)
