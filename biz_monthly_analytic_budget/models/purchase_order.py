# -*- coding: utf-8 -*-
import logging
from datetime import timedelta
from decimal import Decimal
from odoo import api, fields, models, _
from odoo.exceptions import UserError

from .budget_utils import find_active_monthly_plan, extract_analytic_amounts

_logger = logging.getLogger(__name__)

# Keep backward compatibility alias
_extract_po_line_analytic_amounts = extract_analytic_amounts


class PurchaseOrder(models.Model):
    """Extend purchase.order to consume monthly analytic budget on confirmation."""
    _inherit = 'purchase.order'

    payment_date = fields.Date(
        string="Expected Payment",
        compute="_compute_payment_date",
        store=True,
        readonly=False
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

    @api.depends('date_order', 'partner_id', 'partner_id.property_supplier_payment_term_id', 'order_line.date_planned')
    def _compute_payment_date(self):
        for order in self:
            # If manually overridden, we might want to keep it, 
            # but Odoo depends will re-trigger this.
            # In Odoo, to allow manual override on stored compute, 
            # we check if it's already set or if we are in a compute context.
            
            # 1. Manual override is handled by Odoo if we don't overwrite if it exists?
            # Actually, standard pattern is to compute it if it's not set or dependencies changed.
            
            manual_date = order.payment_date
            
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
            
            # 3. Source Requisition payment_date or deadline + 30 days
            # Try to find source requisition
            req_id = False
            if hasattr(order, 'requisition_order'): # field from employee_purchase_requisition
                req = self.env['employee.purchase.requisition'].sudo().search([('name', '=', order.requisition_order)], limit=1)
                if req:
                    if hasattr(req, 'payment_date') and req.payment_date:
                        order.payment_date = req.payment_date
                        continue
                    elif req.requisition_deadline:
                        order.payment_date = req.requisition_deadline + timedelta(days=30)
                        continue
            # Usually PO lines have date_planned.
            if order.order_line:
                dates = order.order_line.mapped('date_planned')
                valid_dates = [d for d in dates if d]
                if valid_dates:
                    order.payment_date = min(valid_dates)
                    continue
            
            # Final fallback
            order.payment_date = (order.date_order or fields.Date.today()) + timedelta(days=30)

    @api.depends(
        'order_line.price_subtotal',
        'order_line.analytic_distribution',
        'payment_date',
    )
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

            if not analytic_totals:
                order.monthly_budget_check_result = _(
                    '<div class="alert alert-info">'
                    'No analytic distribution found on PO lines.'
                    '</div>'
                )
                order.budget_warning = False
                continue

            html_parts = []
            has_warning = False
            AnalyticAccount = self.env['account.analytic.account']
            BudgetLine = self.env['monthly.budget.line']
            has_pr = order._get_source_requisition_id() != order.id
            
            for account_id, po_amt in analytic_totals.items():
                analytic = AnalyticAccount.browse(account_id)
                if not analytic.exists():
                    continue
                dims = {'analytic_account_id': account_id}
                budget_line = BudgetLine._find_budget_line(plan, dims, log_fallback=False)
                if not budget_line:
                    html_parts.append(
                        '<div class="alert alert-warning">No monthly budget line for: %s</div>'
                        % analytic.name
                    )
                    continue
                budget_line = budget_line[0]
                
                # Check if this PO is already reserved
                total_committed = budget_line.reserved_amount + budget_line.used_amount + budget_line.fixed_cost_amount
                if not has_pr:
                    # If direct PO, it's not yet in reserved_amount, so add it for preview
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
                        _('Fixed + Reserved + Used'), '{:,.2f}'.format(budget_line.fixed_cost_amount + budget_line.reserved_amount + budget_line.used_amount),
                        _('This PO'), '{:,.2f}'.format(po_amt),
                        _('Remaining After'), status_class,
                        '{:,.2f}'.format(remaining),
                        _('OK') if not is_over else _('Exceeded!'),
                    )
                )
            order.monthly_budget_check_result = ''.join(html_parts)
            order.budget_warning = has_warning

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

        po_amount = sum(analytic_totals.values())
        
        limit_amt = 0.0
        used = 0.0
        reserved = 0.0
        AnalyticAccount = self.env['account.analytic.account']
        BudgetLine = self.env['monthly.budget.line']
        budget_line_names = []
        has_pr = self._get_source_requisition_id() != self.id
        
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
                if not has_pr:
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

        # 2. Check if approved from source PR
        if hasattr(self, 'requisition_order') and self.requisition_order:
            pr = self.env['employee.purchase.requisition'].search([('name', '=', self.requisition_order)], limit=1)
            if pr:
                approved_pr = ApprovalReq.search([
                    ('document_type', '=', 'pr'),
                    ('ref_pr_id', '=', pr.id),
                    ('state', '=', 'approved'),
                ], limit=1)
                if approved_pr:
                    return

        target_date = self.payment_date
        if not target_date:
            return

        plan = find_active_monthly_plan(self.env, target_date, self.company_id.id)
        if not plan:
            return

        analytic_totals = {}
        for line in self.order_line:
            for account_id, amount in extract_analytic_amounts(line):
                analytic_totals[account_id] = analytic_totals.get(account_id, 0.0) + amount

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
                raise UserError(_(
                    'No monthly budget line found for analytic account "%s".\n'
                    'Please add it to the monthly budget plan "%s" first.'
                ) % (analytic.name, plan.name))

            budget_line = budget_line[:1] or budget_line
            
            # total_committed = already used + already reserved + fixed costs
            total_committed = budget_line.reserved_amount + budget_line.used_amount + budget_line.fixed_cost_amount
            
            # If it's a direct PO (no PR), it hasn't reserved anything yet, so we must add po_amt.
            # If it came from a PR, the PR already reserved it, so it's already in total_committed.
            # However, if the PO amount is higher than what was reserved by PR, we should check that too.
            # For simplicity, if it's a direct PO, we add it. 
            # If it's from PR, we assume it's already in reserved_amount.
            
            has_pr = self._get_source_requisition_id() != self.id
            if not has_pr:
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

        # Aggregate amounts by analytic across all PO lines (Decimal precision)
        analytic_totals = {}
        for line in self.order_line:
            for account_id, amount in extract_analytic_amounts(line, BudgetLine):
                analytic_totals[account_id] = analytic_totals.get(account_id, 0.0) + amount

        if not analytic_totals:
            return

        # --- Concurrency: acquire row-level lock BEFORE reading budget values ---
        BudgetLine._lock_budget_lines(list(analytic_totals.keys()), plan.id)

        # Re-read plan budget lines AFTER acquiring the lock
        plan.invalidate_recordset(['budget_line_ids'])

        for account_id, amount in analytic_totals.items():
            analytic = AnalyticAccount.browse(account_id)
            if not analytic.exists():
                continue
            dims = {'analytic_account_id': account_id}
            budget_line = BudgetLine._find_budget_line(plan, dims)
            if not budget_line:
                continue

            # Update commitment audit records (reserved → used)
            engine.consume_budget({
                'budget_source': 'monthly',
                'document_model': self._name,
                'document_id': self._get_source_requisition_id(),
                'amount': amount,
                'date': target_date,
                'company_id': self.company_id.id,
                'analytic_account_id': account_id,
                'note': _('Consumed by PO %s - %s') % (self.name, analytic.name),
            })
            _logger.info(
                'Monthly budget consumed: PO=%s analytic=%s amount=%.4f plan=%s',
                self.name, analytic.name, amount, plan.name,
            )

    def _get_source_requisition_id(self):
        """
        Try to find the source purchase requisition ID that originated this PO.
        Falls back to PO id if not found.
        """
        self.ensure_one()
        # Check employee.purchase.requisition link
        if hasattr(self, 'requisition_order') and self.requisition_order:
            req = self.env['employee.purchase.requisition'].sudo().search([('name', '=', self.requisition_order)], limit=1)
            if req:
                return req.id
        return self.id

    def button_cancel(self):
        """On PO cancel: release any consumed monthly analytic budget amounts."""
        for order in self:
            if order.state == 'purchase':
                order._release_monthly_analytic_budget_on_cancel()
        result = super().button_cancel()
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

        target_date = self.payment_date
        if not target_date:
            return

        plan = find_active_monthly_plan(self.env, target_date, self.company_id.id)
        if not plan:
            return

        # Mark related commitment records as released
        engine.release_budget({
            'budget_source': 'monthly',
            'document_model': self._name,
            'document_id': self._get_source_requisition_id(),
            'amount': 0,
            'company_id': self.company_id.id,
        })
