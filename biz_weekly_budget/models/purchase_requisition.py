# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


def _find_budget_lines_for_date(env, target_date, company_id):
    """Helper: find confirmed budget lines covering target_date."""
    if not target_date:
        return env['weekly.budget.line']
    domain = [
        ('plan_state', '=', 'confirmed'),
        ('date_from', '<=', target_date),
        ('date_to', '>=', target_date),
        '|',
        ('all_companies', '=', True),
        ('company_id', '=', company_id),
    ]
    return env['weekly.budget.line'].sudo().search(domain)


class EmployeePurchaseRequisition(models.Model):
    _inherit = 'employee.purchase.requisition'

    budget_check_result = fields.Html(
        string='Budget Check Result',
        compute='_compute_budget_check_result',
    )

    def _find_budget_line_for_date(self, target_date):
        """Find the confirmed budget line that covers the given date."""
        domain = [
            ('plan_state', '=', 'confirmed'),
            ('date_from', '<=', target_date),
            ('date_to', '>=', target_date),
        ]
        # Company scope
        company_domain = [
            '|',
            ('all_companies', '=', True),
            ('company_id', '=', self.company_id.id),
        ]
        budget_lines = self.env['weekly.budget.line'].sudo().search(
            domain + company_domain, limit=1
        )
        return budget_lines[:1] if budget_lines else False

    def write(self, vals):
        """Trigger budget reserved recompute when state changes."""
        old_states = {rec.id: rec.state for rec in self}
        result = super().write(vals)
        if 'state' in vals:
            for rec in self:
                if old_states.get(rec.id) != rec.state:
                    target_date = rec.requisition_deadline or rec.request_date
                    budget_lines = _find_budget_lines_for_date(
                        self.env, target_date, rec.company_id.id
                    )
                    if budget_lines:
                        budget_lines._compute_amount_reserved()
        return result

    @api.depends('requisition_order_ids.price_subtotal', 'requisition_deadline')
    def _compute_budget_check_result(self):
        for req in self:
            target_date = req.requisition_deadline or req.request_date
            if not target_date or not req.requisition_order_ids:
                req.budget_check_result = ''
                continue

            budget_line = req._find_budget_line_for_date(target_date)
            if not budget_line:
                req.budget_check_result = _(
                    '<div class="alert alert-info">'
                    'No active weekly budget plan found for the scheduled date.'
                    '</div>'
                )
                continue

            pr_amount = sum(req.requisition_order_ids.mapped('price_subtotal'))
            used = budget_line.amount_used
            limit_amt = budget_line.amount_limit
            total_after = used + pr_amount
            remaining = limit_amt - total_after
            is_over = remaining < 0

            if is_over:
                status_class = 'danger'
                status_icon = '&#10060;'
                status_text = _('Exceeded!')
            else:
                status_class = 'success'
                status_icon = '&#9989;'
                status_text = _('OK')

            req.budget_check_result = (
                '<div class="card mb-2 border-%s">'
                '<div class="card-body p-2">'
                '<h6 class="card-title">%s %s (PR - Estimate)</h6>'
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
                    _('Already Used (Confirmed POs)'),
                    '{:,.2f}'.format(used),
                    _('This PR Amount (Estimate)'),
                    '{:,.2f}'.format(pr_amount),
                    _('Total (Estimate)'),
                    '{:,.2f}'.format(total_after),
                    _('Remaining (Estimate)'),
                    status_class,
                    '{:,.2f}'.format(remaining),
                    status_text,
                )
            )

    def action_check_budget(self):
        """Button action to trigger budget check recomputation."""
        self.ensure_one()
        self._compute_budget_check_result()
        return True

    def action_head_approval(self):
        """Override to check weekly budget before head approval."""
        for req in self:
            req._check_weekly_budget()
        return super().action_head_approval()

    def _check_weekly_budget(self):
        """Check if this PR would exceed any weekly budget."""
        self.ensure_one()
        target_date = self.requisition_deadline or self.request_date
        if not target_date or not self.requisition_order_ids:
            return

        budget_line = self._find_budget_line_for_date(target_date)
        if not budget_line:
            return  # No budget plan active, allow approval

        pr_amount = sum(self.requisition_order_ids.mapped('price_subtotal'))
        used = budget_line.amount_used
        limit_amt = budget_line.amount_limit
        total_after = used + pr_amount
        overage = total_after - limit_amt

        if overage > 0:
            # Post to budget plan chatter
            budget_line.plan_id.message_post(
                body=_(
                    '<strong>Budget Exceeded Alert (PR)</strong><br/>'
                    'PR: <strong>%s</strong><br/>'
                    'User: %s<br/>'
                    'Week: %s<br/>'
                    'Budget: %s | Used: %s | PR Amount: %s | Over by: %s'
                ) % (
                    self.name,
                    self.env.user.name,
                    budget_line.name,
                    '{:,.2f}'.format(limit_amt),
                    '{:,.2f}'.format(used),
                    '{:,.2f}'.format(pr_amount),
                    '{:,.2f}'.format(overage),
                ),
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )

            raise UserError(_(
                'Weekly Budget Exceeded! Cannot approve Purchase Requisition.\n\n'
                'Week: %s\n'
                '  - Budget Limit: %s\n'
                '  - Already Used: %s\n'
                '  - This PR: %s\n'
                '  - Over by: %s'
            ) % (
                budget_line.name,
                '{:,.2f}'.format(limit_amt),
                '{:,.2f}'.format(used),
                '{:,.2f}'.format(pr_amount),
                '{:,.2f}'.format(overage),
            ))
