# -*- coding: utf-8 -*-
import logging
from collections import defaultdict

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    # Budget info fields (computed on demand via button)
    budget_check_result = fields.Html(
        string='Budget Check Result',
        compute='_compute_budget_check_result',
    )
    budget_warning = fields.Boolean(
        string='Budget Warning',
        compute='_compute_budget_check_result',
    )

    def write(self, vals):
        """Trigger budget reserved recompute when PO state changes."""
        old_states = {rec.id: rec.state for rec in self}
        result = super().write(vals)
        if 'state' in vals:
            BudgetLine = self.env['weekly.budget.line'].sudo()
            for rec in self:
                if old_states.get(rec.id) != rec.state:
                    for po_line in rec.order_line:
                        if not po_line.date_planned:
                            continue
                        line_date = (po_line.date_planned.date()
                                     if hasattr(po_line.date_planned, 'date')
                                     else po_line.date_planned)
                        budget_lines = BudgetLine.search([
                            ('plan_state', '=', 'confirmed'),
                            ('date_from', '<=', line_date),
                            ('date_to', '>=', line_date),
                            '|',
                            ('all_companies', '=', True),
                            ('company_id', '=', rec.company_id.id),
                        ])
                        if budget_lines:
                            budget_lines._compute_amount_reserved()
        return result

    def _get_weekly_budget_lines_for_po(self):
        """Return dict: {budget_line: po_line_amount} for this PO's lines grouped by week."""
        self.ensure_one()
        result = defaultdict(float)

        for po_line in self.order_line:
            scheduled_date = po_line.date_planned
            if not scheduled_date:
                continue

            line_date = scheduled_date.date() if hasattr(scheduled_date, 'date') else scheduled_date

            # Find matching budget line
            budget_line = self._find_budget_line_for_date(line_date)
            if budget_line:
                result[budget_line] += po_line.price_subtotal

        return result

    def _find_budget_line_for_date(self, target_date):
        """Find the confirmed budget line that covers the given date."""
        domain = [
            ('plan_state', '=', 'confirmed'),
            ('date_from', '<=', target_date),
            ('date_to', '>=', target_date),
        ]

        # Company scope: find plans for this PO's company OR all-companies plans
        company_domain = [
            '|',
            ('all_companies', '=', True),
            ('company_id', '=', self.company_id.id),
        ]

        budget_lines = self.env['weekly.budget.line'].sudo().search(
            domain + company_domain, limit=1
        )
        return budget_lines[:1] if budget_lines else False

    @api.depends('order_line.date_planned', 'order_line.price_subtotal')
    def _compute_budget_check_result(self):
        for order in self:
            if not order.order_line:
                order.budget_check_result = ''
                order.budget_warning = False
                continue

            week_amounts = order._get_weekly_budget_lines_for_po()
            if not week_amounts:
                order.budget_check_result = _(
                    '<div class="alert alert-info">'
                    'No active weekly budget plan found for the scheduled dates.'
                    '</div>'
                )
                order.budget_warning = False
                continue

            html_parts = []
            has_warning = False

            for budget_line, po_amount in week_amounts.items():
                used = budget_line.amount_used
                limit_amt = budget_line.amount_limit
                # Exclude current PO if already confirmed (re-check scenario)
                if order.state in ('purchase', 'done'):
                    # Subtract this PO's contribution that's already counted
                    current_po_in_used = self._get_po_amount_in_budget_line(
                        order, budget_line
                    )
                    used -= current_po_in_used

                total_after = used + po_amount
                remaining = limit_amt - total_after
                is_over = remaining < 0

                if is_over:
                    has_warning = True
                    status_class = 'danger'
                    status_icon = '&#10060;'
                    status_text = _('Exceeded!')
                else:
                    status_class = 'success'
                    status_icon = '&#9989;'
                    status_text = _('OK')

                html_parts.append(
                    '<div class="card mb-2 border-%s">'
                    '<div class="card-body p-2">'
                    '<h6 class="card-title">%s %s</h6>'
                    '<table class="table table-sm table-borderless mb-0">'
                    '<tr><td>%s</td><td class="text-end">%s</td></tr>'
                    '<tr><td>%s</td><td class="text-end">%s</td></tr>'
                    '<tr><td>%s</td><td class="text-end">%s</td></tr>'
                    '<tr class="border-top"><td><strong>%s</strong></td>'
                    '<td class="text-end"><strong>%s</strong></td></tr>'
                    '<tr><td><strong>%s</strong></td>'
                    '<td class="text-end text-%s"><strong>%s %s</strong></td></tr>'
                    '</table>'
                    '</div></div>' % (
                        status_class,
                        status_icon,
                        budget_line.name,
                        _('Weekly Budget'),
                        '{:,.2f}'.format(limit_amt),
                        _('Already Used (Other POs)'),
                        '{:,.2f}'.format(used),
                        _('This PO Amount'),
                        '{:,.2f}'.format(po_amount),
                        _('Total After Confirm'),
                        '{:,.2f}'.format(total_after),
                        _('Remaining After Confirm'),
                        status_class,
                        '{:,.2f}'.format(remaining),
                        status_text,
                    )
                )

            order.budget_check_result = ''.join(html_parts)
            order.budget_warning = has_warning

    def _get_po_amount_in_budget_line(self, po, budget_line):
        """Get how much of this PO is already counted in the budget line's used amount."""
        total = 0.0
        for po_line in po.order_line:
            if not po_line.date_planned:
                continue
            line_date = po_line.date_planned.date() if hasattr(po_line.date_planned, 'date') else po_line.date_planned
            if budget_line.date_from <= line_date <= budget_line.date_to:
                total += po_line.price_subtotal
        return total

    def action_check_budget(self):
        """Button action to trigger budget check recomputation."""
        self.ensure_one()
        # Force recompute
        self._compute_budget_check_result()
        return True

    def action_submit_for_review(self):
        """Override to check weekly budget before sending for review."""
        for order in self:
            order._check_weekly_budget()
        return super().action_submit_for_review()

    def button_confirm(self):
        """Override to check weekly budget before confirming."""
        for order in self:
            order._check_weekly_budget()
        return super().button_confirm()

    def _check_weekly_budget(self):
        """Check if confirming this PO would exceed any weekly budget."""
        self.ensure_one()
        week_amounts = self._get_weekly_budget_lines_for_po()

        if not week_amounts:
            return  # No budget plan active, allow confirmation

        violations = []
        for budget_line, po_amount in week_amounts.items():
            used = budget_line.amount_used
            limit_amt = budget_line.amount_limit
            total_after = used + po_amount
            overage = total_after - limit_amt

            if overage > 0:
                violations.append({
                    'line': budget_line,
                    'limit': limit_amt,
                    'used': used,
                    'po_amount': po_amount,
                    'overage': overage,
                })

        if violations:
            self._handle_budget_violation(violations)

    def _handle_budget_violation(self, violations):
        """Block PO confirmation and send notification."""
        self.ensure_one()

        # Build error message
        msg_parts = [_('Weekly Budget Exceeded! Cannot proceed with Purchase Order.\n')]
        for v in violations:
            msg_parts.append(
                _('Week: %s\n'
                  '  - Budget Limit: %s\n'
                  '  - Already Used: %s\n'
                  '  - This PO: %s\n'
                  '  - Over by: %s\n') % (
                    v['line'].name,
                    '{:,.2f}'.format(v['limit']),
                    '{:,.2f}'.format(v['used']),
                    '{:,.2f}'.format(v['po_amount']),
                    '{:,.2f}'.format(v['overage']),
                )
            )

        # Send email notification
        self._send_budget_exceeded_notification(violations)

        # Post to budget plan chatter
        for v in violations:
            plan = v['line'].plan_id
            plan.message_post(
                body=_(
                    '<strong>Budget Exceeded Alert</strong><br/>'
                    'PO: <strong>%s</strong><br/>'
                    'User: %s<br/>'
                    'Week: %s<br/>'
                    'Budget: %s | Used: %s | PO Amount: %s | Over by: %s'
                ) % (
                    self.name,
                    self.env.user.name,
                    v['line'].name,
                    '{:,.2f}'.format(v['limit']),
                    '{:,.2f}'.format(v['used']),
                    '{:,.2f}'.format(v['po_amount']),
                    '{:,.2f}'.format(v['overage']),
                ),
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )

        raise UserError('\n'.join(msg_parts))

    def _send_budget_exceeded_notification(self, violations):
        """Send email to notify users about budget exceeded."""
        template = self.env.ref(
            'biz_weekly_budget.mail_template_budget_exceeded',
            raise_if_not_found=False,
        )
        if not template:
            return

        # Collect all notify users from related plans
        notify_users = self.env['res.users']
        for v in violations:
            notify_users |= v['line'].plan_id.notify_user_ids

        if not notify_users:
            return

        # Build violation details for email context
        violation_details = []
        for v in violations:
            violation_details.append({
                'week_name': v['line'].name,
                'limit': '{:,.2f}'.format(v['limit']),
                'used': '{:,.2f}'.format(v['used']),
                'po_amount': '{:,.2f}'.format(v['po_amount']),
                'overage': '{:,.2f}'.format(v['overage']),
                'plan_name': v['line'].plan_id.name,
            })

        for user in notify_users:
            if not user.email:
                continue
            try:
                template.with_context(
                    violation_details=violation_details,
                    notify_email=user.email,
                    notify_name=user.name,
                    po_name=self.name,
                    po_user=self.env.user.name,
                ).send_mail(self.id, force_send=False)
            except Exception as e:
                _logger.warning(
                    'Failed to send budget exceeded email to %s: %s',
                    user.email, str(e)
                )
