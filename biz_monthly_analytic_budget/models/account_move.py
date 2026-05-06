# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models

from .budget_utils import (
    extract_analytic_amounts,
    filter_analytic_totals_for_plan,
    find_active_monthly_plan,
    format_ignored_analytic_accounts_message,
    format_missing_budget_line_message,
    format_no_analytic_distribution_message,
)

from odoo.exceptions import UserError
from markupsafe import escape
from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    monthly_bill_due_date_from_po = fields.Boolean(
        string='Bill Due Date Auto-filled from PO',
        copy=False,
        default=False,
        readonly=True,
    )
    monthly_budget_plan_id = fields.Many2one(
        'monthly.budget.plan',
        string='Budget Plan',
        compute='_compute_monthly_budget_plan_id',
        store=True,
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
                ('document_type', '=', 'bill'),
                ('ref_bill_id', '=', rec.id),
            ], limit=1, order='id desc')
            
            # Check PO fallback
            if not req and rec._get_related_purchase_order():
                pos = rec._get_related_purchase_order()
                if pos:
                    req = ApprovalReq.search([
                        ('document_type', '=', 'po'),
                        ('ref_po_id', 'in', pos.ids),
                    ], limit=1, order='id desc')
            rec.buz_budget_approval_id = req

    @api.depends('invoice_date_due', 'invoice_origin', 'purchase_id', 'company_id')
    def _compute_monthly_budget_plan_id(self):
        for move in self:
            if move.move_type not in ('in_invoice', 'in_refund'):
                move.monthly_budget_plan_id = False
                continue
            target_date = move._get_bill_target_date()
            if target_date:
                plan = find_active_monthly_plan(self.env, target_date, move.company_id.id)
                move.monthly_budget_plan_id = plan.id if plan else False
            else:
                move.monthly_budget_plan_id = False

    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        moves._sync_monthly_bill_budget()
        for move in moves:
            source_po = move._get_related_purchase_order()
            if source_po:
                for po in source_po:
                    if po.state in ('purchase', 'done'):
                        po._consume_monthly_analytic_budget()
        return moves

    def write(self, vals):
        prev_states = {rec.id: rec.state for rec in self}
        if 'invoice_date_due' in vals and not self.env.context.get('skip_monthly_bill_budget_sync'):
            vals = dict(vals)
            vals['monthly_bill_due_date_from_po'] = False
        result = super().write(vals)
        if not self.env.context.get('skip_monthly_bill_budget_sync') and any(key in vals for key in (
            'state',
            'invoice_date_due',
            'invoice_date',
            'date',
            'invoice_line_ids',
            'line_ids',
            'invoice_origin',
            'purchase_id',
        )):
            for move in self:
                prev_state = prev_states.get(move.id)
                move._sync_monthly_bill_budget(previous_state=prev_state)
                
                # Trigger PO to recalculate its unbilled reserved amount
                source_po = move._get_related_purchase_order()
                if source_po:
                    for po in source_po:
                        if po.state in ('purchase', 'done'):
                            po._consume_monthly_analytic_budget()
        return result

    def action_post(self):
        """Synchronize monthly budget when vendor bills are posted."""
        for move in self:
            if move.move_type in ('in_invoice', 'in_refund'):
                move._check_monthly_analytic_budget_limit()
        return super().action_post()

    def button_draft(self):
        """Synchronize monthly budget when a bill is reset to draft."""
        return super().button_draft()

    def unlink(self):
        """Release monthly budget commitments before deleting bills."""
        bills = self.filtered(lambda move: move.move_type in ('in_invoice', 'in_refund'))
        
        # Keep track of related POs to update them AFTER bills are deleted
        pos_to_update = self.env['purchase.order'].browse()
        for move in bills:
            source_po = move._get_related_purchase_order()
            if source_po:
                pos_to_update |= source_po
            move._release_monthly_bill_budget_by_state()
            
        res = super().unlink()
        
        # Trigger PO to recalculate its unbilled reserved amount so the reserved amount comes back
        for po in pos_to_update:
            if po.exists() and po.state in ('purchase', 'done'):
                po._consume_monthly_analytic_budget()
                
        return res

    def _sync_monthly_bill_budget(self, previous_state=None):
        """Synchronize bill commitments based on source and current state."""
        BudgetLine = self.env['monthly.budget.line']
        engine = self.env['budget.engine']
        for move in self:
            if move.move_type not in ('in_invoice', 'in_refund'):
                continue

            source_po = move._get_related_purchase_order()
            if source_po:
                po_target_date = move._get_purchase_order_target_date(source_po)
                if move.state == 'draft' and po_target_date and (
                    not move.invoice_date_due or move.monthly_bill_due_date_from_po
                ):
                    move.with_context(skip_monthly_bill_budget_sync=True).write({
                        'invoice_date_due': po_target_date,
                        'monthly_bill_due_date_from_po': True,
                    })
                # No longer skipping! PO-linked bills now consume their own portion
                # of the budget, while the PO reserves the unbilled amount.

            target_date = move._get_bill_target_date()
            if not target_date:
                continue

            plan = find_active_monthly_plan(self.env, target_date, move.company_id.id)
            if not plan:
                continue

            analytic_totals = {}
            for line in move.invoice_line_ids:
                for account_id, amount in extract_analytic_amounts(line, BudgetLine):
                    analytic_totals[account_id] = analytic_totals.get(account_id, 0.0) + amount

            analytic_totals, _ignored_totals = filter_analytic_totals_for_plan(plan, analytic_totals)
            if not analytic_totals:
                continue

            if move.state == 'cancel':
                move._release_monthly_bill_budget(plan, analytic_totals, target_date)
                continue

            # Both draft and posted bills are considered "used" budget
            if move.state in ('draft', 'posted'):
                move._sync_monthly_bill_usage(plan, analytic_totals, target_date)

    def _get_related_purchase_order(self):
        """Return the PO(s) linked to this bill, if any."""
        self.ensure_one()
        purchase = getattr(self, 'purchase_id', self.env['purchase.order'].browse())
        if purchase and purchase.exists():
            return purchase

        # Odoo 15+ reliable way to link bill to PO
        if hasattr(self, 'invoice_line_ids') and any(hasattr(line, 'purchase_line_id') for line in self.invoice_line_ids):
            po_lines = self.invoice_line_ids.mapped('purchase_line_id')
            if po_lines:
                return po_lines.mapped('order_id')

        origin = (self.invoice_origin or '').strip()
        if not origin:
            return self.env['purchase.order'].browse()

        # Handle comma-separated origins (e.g. 'PO001, PO002')
        origin_list = [o.strip() for o in origin.split(',') if o.strip()]
        
        return self.env['purchase.order'].sudo().search([
            '|',
            ('name', 'in', origin_list),
            ('requisition_order', 'in', origin_list),
        ])

    def _get_purchase_order_target_date(self, source_po=None):
        """Return the PO's expected payment date for budget alignment."""
        self.ensure_one()
        source_po = source_po or self._get_related_purchase_order()
        if not source_po:
            return False
        # Use the first PO that has a valid date
        for po in source_po:
            date = po.payment_date or (po.date_order.date() if po.date_order else False)
            if date:
                return date
        return False

    def _get_bill_target_date(self):
        """Return the date used to match the bill against a budget plan."""
        self.ensure_one()
        if self.invoice_date_due:
            return self.invoice_date_due

        source_po = self._get_related_purchase_order()
        if source_po:
            return self._get_purchase_order_target_date(source_po)

        return False

    def _sync_monthly_bill_reservation(self, plan, analytic_totals, target_date):
        """Keep draft direct bills as reserved commitments (upsert — no duplicate creation)."""
        BudgetLine = self.env['monthly.budget.line']
        engine = self.env['budget.engine']
        Commitment = self.env['budget.commitment'].sudo()
        AnalyticAccount = self.env['account.analytic.account']

        BudgetLine._lock_budget_lines(list(analytic_totals.keys()), plan.id)
        plan._refresh_budget_snapshot(refresh_report=False)

        # Track which analytic accounts were processed so we can release stale ones
        processed_account_ids = set()

        for account_id, amount in analytic_totals.items():
            if not amount:
                continue
            analytic = AnalyticAccount.browse(account_id)
            if not analytic.exists():
                continue
            if not BudgetLine._find_budget_line(plan, {'analytic_account_id': account_id}, log_fallback=False):
                continue

            processed_account_ids.add(account_id)
            note = 'Reserved from Bill %s - %s' % (self.name, analytic.name)

            # Search existing BEFORE any release to avoid duplicate creation
            existing_reserved = Commitment.search([
                ('document_model', '=', self._name),
                ('document_id', '=', self.id),
                ('analytic_account_id', '=', account_id),
                ('budget_source', '=', 'monthly'),
                ('state', '=', 'reserved'),
            ])
            existing_used = Commitment.search([
                ('document_model', '=', self._name),
                ('document_id', '=', self.id),
                ('analytic_account_id', '=', account_id),
                ('budget_source', '=', 'monthly'),
                ('state', '=', 'used'),
            ])
            
            all_existing = existing_reserved | existing_used
            
            if all_existing:
                primary = all_existing[0]
                if primary.amount != amount or primary.date != target_date or primary.state != 'reserved':
                    primary.write({'amount': amount, 'date': target_date, 'state': 'reserved', 'note': note})
                if len(all_existing) > 1:
                    all_existing[1:].action_release()
            else:
                engine.reserve_budget({
                    'budget_source': 'monthly',
                    'document_model': self._name,
                    'document_id': self.id,
                    'amount': amount,
                    'date': target_date,
                    'company_id': self.company_id.id,
                    'analytic_account_id': account_id,
                    'note': note,
                })

        # Release stale commitments for analytics that are no longer on this bill
        if processed_account_ids is not None:
            stale = Commitment.search([
                ('document_model', '=', self._name),
                ('document_id', '=', self.id),
                ('budget_source', '=', 'monthly'),
                ('state', 'in', ('reserved', 'used')),
                ('analytic_account_id', 'not in', list(processed_account_ids)),
            ])
            if stale:
                stale.action_release()

        plan._refresh_budget_snapshot(refresh_report=True)

    def _sync_monthly_bill_usage(self, plan, analytic_totals, target_date):
        """Keep bills in used state, converting any draft reservation if needed (upsert — no duplicate)."""
        BudgetLine = self.env['monthly.budget.line']
        engine = self.env['budget.engine']
        Commitment = self.env['budget.commitment'].sudo()
        AnalyticAccount = self.env['account.analytic.account']

        BudgetLine._lock_budget_lines(list(analytic_totals.keys()), plan.id)
        plan._refresh_budget_snapshot(refresh_report=False)

        processed_account_ids = set()

        for account_id, amount in analytic_totals.items():
            if not amount:
                continue
            analytic = AnalyticAccount.browse(account_id)
            if not analytic.exists():
                continue
            if not BudgetLine._find_budget_line(plan, {'analytic_account_id': account_id}, log_fallback=False):
                continue

            processed_account_ids.add(account_id)
            note = 'Consumed by Bill %s - %s' % (self.name, analytic.name)

            # Search existing BEFORE any release to avoid duplicate creation
            existing_used = Commitment.search([
                ('document_model', '=', self._name),
                ('document_id', '=', self.id),
                ('analytic_account_id', '=', account_id),
                ('budget_source', '=', 'monthly'),
                ('state', '=', 'used'),
            ])
            existing_reserved = Commitment.search([
                ('document_model', '=', self._name),
                ('document_id', '=', self.id),
                ('analytic_account_id', '=', account_id),
                ('budget_source', '=', 'monthly'),
                ('state', '=', 'reserved'),
            ])
            
            all_existing = existing_used | existing_reserved
            
            if all_existing:
                primary = all_existing[0]
                if primary.amount != amount or primary.date != target_date or primary.state != 'used':
                    primary.write({'amount': amount, 'date': target_date, 'state': 'used', 'note': note})
                if len(all_existing) > 1:
                    all_existing[1:].action_release()
            else:
                engine.consume_budget({
                    'budget_source': 'monthly',
                    'document_model': self._name,
                    'document_id': self.id,
                    'amount': amount,
                    'date': target_date,
                    'company_id': self.company_id.id,
                    'analytic_account_id': account_id,
                    'note': note,
                })

        # Release stale commitments for analytics that are no longer on this bill
        if processed_account_ids is not None:
            stale = Commitment.search([
                ('document_model', '=', self._name),
                ('document_id', '=', self.id),
                ('budget_source', '=', 'monthly'),
                ('state', 'in', ('reserved', 'used')),
                ('analytic_account_id', 'not in', list(processed_account_ids)),
            ])
            if stale:
                stale.action_release()

        plan._refresh_budget_snapshot(refresh_report=True)

    def _release_monthly_bill_budget(self, plan, analytic_totals, target_date):
        BudgetLine = self.env['monthly.budget.line']
        engine = self.env['budget.engine']

        BudgetLine._lock_budget_lines(list(analytic_totals.keys()), plan.id)
        plan._refresh_budget_snapshot(refresh_report=False)

        engine.release_budget({
            'budget_source': 'monthly',
            'document_model': self._name,
            'document_id': self.id,
            'amount': 0,
            'company_id': self.company_id.id,
        })

        plan._refresh_budget_snapshot(refresh_report=True)

    def _release_monthly_bill_budget_by_state(self):
        """Release all monthly bill commitments regardless of current amount/state."""
        for move in self:
            target_date = move._get_bill_target_date()
            if not target_date:
                target_date = fields.Date.context_today(move)
            plan = find_active_monthly_plan(self.env, target_date, move.company_id.id)
            analytic_totals = {}
            if plan:
                BudgetLine = self.env['monthly.budget.line']
                for line in move.invoice_line_ids:
                    for account_id, amount in extract_analytic_amounts(line, BudgetLine):
                        analytic_totals[account_id] = analytic_totals.get(account_id, 0.0) + amount
                analytic_totals, _ignored_totals = filter_analytic_totals_for_plan(plan, analytic_totals)
            if not plan or not analytic_totals:
                self.env['budget.engine'].release_budget({
                    'budget_source': 'monthly',
                    'document_model': move._name,
                    'document_id': move.id,
                    'amount': 0,
                    'company_id': move.company_id.id,
                })
                continue

            move._release_monthly_bill_budget(plan, analytic_totals, target_date)

    @api.depends('invoice_line_ids.price_subtotal', 'invoice_line_ids.analytic_distribution', 'invoice_date_due', 'date', 'invoice_date')
    def _compute_monthly_budget_check(self):
        for move in self:
            if move.move_type not in ('in_invoice', 'in_refund'):
                move.monthly_budget_check_result = ''
                move.budget_warning = False
                continue
                
            target_date = move._get_bill_target_date()
            if not target_date or not move.invoice_line_ids:
                move.monthly_budget_check_result = ''
                move.budget_warning = False
                continue

            plan = find_active_monthly_plan(self.env, target_date, move.company_id.id)
            if not plan:
                move.monthly_budget_check_result = _(
                    '<div class="alert alert-info">No active monthly analytic budget plan found for the target date.</div>'
                )
                move.budget_warning = False
                continue

            analytic_totals = {}
            for line in move.invoice_line_ids:
                for account_id, amount in extract_analytic_amounts(line, self.env['monthly.budget.line']):
                    analytic_totals[account_id] = analytic_totals.get(account_id, 0.0) + amount

            analytic_totals, ignored_totals = filter_analytic_totals_for_plan(plan, analytic_totals)

            if not analytic_totals:
                move.monthly_budget_check_result = _('<div class="alert alert-info">No matching budget lines.</div>')
                move.budget_warning = False
                continue

            html_parts = []
            has_warning = False
            AnalyticAccount = self.env['account.analytic.account']
            BudgetLine = self.env['monthly.budget.line']
            
            source_pos = move._get_related_purchase_order()
            has_po = bool(source_pos)
            
            for account_id, bill_amt in analytic_totals.items():
                analytic = AnalyticAccount.browse(account_id)
                if not analytic.exists():
                    continue
                dims = {'analytic_account_id': account_id}
                budget_line = BudgetLine._find_budget_line(plan, dims, log_fallback=False)
                if not budget_line:
                    html_parts.append('<div class="alert alert-warning">%s</div>' % format_missing_budget_line_message(analytic.name, plan.name))
                    continue
                budget_line = budget_line[0]
                
                total_committed = budget_line.reserved_amount + budget_line.used_amount
                
                # Direct bill, not yet saved/consumed
                if not has_po and move.state not in ('draft', 'posted'):
                    total_committed += bill_amt
                    
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
                    '<tr class="border-top"><td><strong>%s</strong></td>'
                    '<td class="text-end text-%s"><strong>%s %s</strong></td></tr>'
                    '</table></div></div>' % (
                        status_class, status_icon, analytic.name,
                        _('Monthly Budget'), '{:,.2f}'.format(budget_line.budget_amount),
                        _('Reserved + Used'), '{:,.2f}'.format(budget_line.reserved_amount + budget_line.used_amount),
                        _('Remaining After'), status_class, '{:,.2f}'.format(remaining),
                        _('OK') if not is_over else _('Exceeded!'),
                    )
                )
            move.monthly_budget_check_result = ''.join(html_parts)
            move.budget_warning = has_warning

    def action_check_monthly_budget(self):
        self.ensure_one()
        self._compute_monthly_budget_check()
        return True

    def action_request_monthly_budget_approval(self):
        self.ensure_one()
        target_date = self._get_bill_target_date()
        plan = find_active_monthly_plan(self.env, target_date, self.company_id.id)
        if not plan:
            return

        analytic_totals = {}
        for line in self.invoice_line_ids:
            for account_id, amount in extract_analytic_amounts(line, self.env['monthly.budget.line']):
                analytic_totals[account_id] = analytic_totals.get(account_id, 0.0) + amount

        analytic_totals, _ignored_totals = filter_analytic_totals_for_plan(plan, analytic_totals)
        if not analytic_totals:
            return

        bill_amount = sum(analytic_totals.values())
        limit_amt = 0.0
        used = 0.0
        reserved = 0.0
        budget_line_names = []
        BudgetLine = self.env['monthly.budget.line']
        
        for account_id, amt in analytic_totals.items():
            dims = {'analytic_account_id': account_id}
            bl = BudgetLine._find_budget_line(plan, dims, log_fallback=False)
            if bl:
                limit_amt += bl.budget_amount
                used += bl.used_amount
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
                'default_document_type': 'bill',
                'default_ref_id': self.id,
                'default_budget_line_names': ', '.join(budget_line_names),
                'default_amount_requested': bill_amount,
                'default_amount_used': used,
                'default_amount_reserved': reserved,
                'default_amount_limit': limit_amt,
                'default_amount_overage': overage,
                'default_plan_id': plan.id,
            }
        }

    def _check_monthly_analytic_budget_limit(self):
        self.ensure_one()
        ApprovalReq = self.env['buz.monthly.budget.approval.request'].sudo()
        
        # Bypass if approved
        approved_bill = ApprovalReq.search([
            ('document_type', '=', 'bill'),
            ('ref_bill_id', '=', self.id),
            ('state', '=', 'approved'),
        ], limit=1)
        if approved_bill:
            return
            
        # Bypass if linked to approved PO
        source_pos = self._get_related_purchase_order()
        if source_pos:
            approved_po = ApprovalReq.search([
                ('document_type', '=', 'po'),
                ('ref_po_id', 'in', source_pos.ids),
                ('state', '=', 'approved'),
            ], limit=1)
            if approved_po:
                return

        target_date = self._get_bill_target_date()
        if not target_date:
            return

        plan = find_active_monthly_plan(self.env, target_date, self.company_id.id)
        if not plan:
            return

        analytic_totals = {}
        for line in self.invoice_line_ids:
            for account_id, amount in extract_analytic_amounts(line, self.env['monthly.budget.line']):
                analytic_totals[account_id] = analytic_totals.get(account_id, 0.0) + amount

        analytic_totals, _ignored_totals = filter_analytic_totals_for_plan(plan, analytic_totals)
        if not analytic_totals:
            return

        AnalyticAccount = self.env['account.analytic.account']
        BudgetLine = self.env['monthly.budget.line']
        violations = []
        for account_id, bill_amt in analytic_totals.items():
            analytic = AnalyticAccount.browse(account_id)
            if not analytic.exists():
                continue
            dims = {'analytic_account_id': account_id}
            budget_line = BudgetLine._find_budget_line(plan, dims)
            if not budget_line:
                raise UserError(format_missing_budget_line_message(analytic.name, plan.name))

            budget_line = budget_line[:1]
            total_committed = budget_line.reserved_amount + budget_line.used_amount
            
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
                    'Analytic: %s\n  Budget: %s | Committed: %s | Over by: %s\n'
                ) % (v['analytic'], '{:,.2f}'.format(v['budget']), '{:,.2f}'.format(v['committed']), '{:,.2f}'.format(v['overage'])))
            msg_lines.append(_('\nPlease click "Request Budget Approval" button on the bill.'))
            raise UserError('\n'.join(msg_lines))
