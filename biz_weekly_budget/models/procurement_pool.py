# -*- coding: utf-8 -*-
from datetime import timedelta
from odoo import api, fields, models, _
from odoo.exceptions import UserError

class ProcurementPool(models.Model):
    _inherit = 'procurement.pool'

    payment_date = fields.Date(
        string='Expected Payment',
        compute='_compute_payment_date',
        store=True,
        readonly=False,
        help="Expected date of cash outflow. Default is Today + 30 days."
    )

    budget_check_result = fields.Html(
        string='Budget Check Result',
        compute='_compute_budget_check_result',
    )
    
    budget_warning = fields.Boolean(
        string='Budget Warning',
        compute='_compute_budget_check_result',
    )

    @api.depends('create_date')
    def _compute_payment_date(self):
        for pool in self:
            if pool.payment_date:
                continue
            base_date = fields.Date.to_date(pool.create_date) if pool.create_date else fields.Date.today()
            pool.payment_date = base_date + timedelta(days=30)

    def _find_budget_line_for_date(self, target_date):
        """Find the confirmed budget line that covers the given date."""
        domain = [
            ('plan_state', '=', 'confirmed'),
            ('date_from', '<=', target_date),
            ('date_to', '>=', target_date),
        ]
        
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
        """Trigger budget reserved recompute when state or payment_date changes."""
        old_data = {rec.id: {'state': rec.state, 'payment_date': rec.payment_date} for rec in self}
        result = super().write(vals)
        if 'state' in vals or 'payment_date' in vals:
            for rec in self:
                dates_to_update = set()
                if old_data[rec.id]['payment_date']:
                    dates_to_update.add(old_data[rec.id]['payment_date'])
                if rec.payment_date:
                    dates_to_update.add(rec.payment_date)
                
                for target_date in dates_to_update:
                    budget_lines = self.env['weekly.budget.line'].sudo().search([
                        ('plan_state', '=', 'confirmed'),
                        ('date_from', '<=', target_date),
                        ('date_to', '>=', target_date),
                        '|',
                        ('all_companies', '=', True),
                        ('company_id', '=', rec.company_id.id),
                    ])
                    if budget_lines:
                        budget_lines._compute_amount_used()
                        budget_lines._compute_amount_reserved()
        return result

    @api.depends('line_ids.total_qty', 'line_ids.price_unit', 'payment_date')
    def _compute_budget_check_result(self):
        for pool in self:
            target_date = pool.payment_date
            if not target_date or not pool.line_ids:
                pool.budget_check_result = ''
                pool.budget_warning = False
                continue

            budget_line = pool._find_budget_line_for_date(target_date)
            if not budget_line:
                pool.budget_check_result = _(
                    '<div class="alert alert-info">'
                    'No active weekly budget plan found for the expected payment date.'
                    '</div>'
                )
                pool.budget_warning = False
                continue

            pool_amount = sum(line.total_qty * line.price_unit for line in pool.line_ids)
            used = budget_line.amount_used
            reserved = budget_line.amount_reserved
            limit_amt = budget_line.amount_limit
            
            # Since this pool is an estimate, we check if it fits the budget limit minus used amount
            total_after = used + pool_amount
            remaining = limit_amt - total_after
            is_over = remaining < 0

            if is_over:
                pool.budget_warning = True
                status_class = 'danger'
                status_icon = '&#10060;'
                status_text = _('Exceeded!')
            else:
                pool.budget_warning = False
                status_class = 'success'
                status_icon = '&#9989;'
                status_text = _('OK')

            pool.budget_check_result = (
                '<div class="card mb-2 border-%s">'
                '<div class="card-body p-2">'
                '<h6 class="card-title">%s %s (Pool - Estimate)</h6>'
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
                    _('Weekly Budget Limit'),
                    '{:,.2f}'.format(limit_amt),
                    _('Already Used (Confirmed POs)'),
                    '{:,.2f}'.format(used),
                    _('This Pool Amount (Estimate)'),
                    '{:,.2f}'.format(pool_amount),
                    _('Projected Total'),
                    '{:,.2f}'.format(total_after),
                    _('Remaining (Estimate)'),
                    status_class,
                    '{:,.2f}'.format(remaining),
                    status_text,
                )
            )

    def action_check_budget(self):
        self.ensure_one()
        self._compute_budget_check_result()
        return True

    def action_confirm(self):
        """Override to check weekly budget before confirming."""
        for pool in self:
            pool._check_weekly_budget()
        return super().action_confirm()

    def action_create_rfq(self):
        """Override to check weekly budget before creating RFQs."""
        for pool in self:
            pool._check_weekly_budget()
        
        res = super().action_create_rfq()
        
        for pool in self:
            if pool.payment_date:
                pos = self.env['purchase.order'].search([
                    ('procurement_pool_id', '=', pool.id),
                    ('state', '=', 'draft')
                ])
                for po in pos:
                    po.payment_date = pool.payment_date
                    
        return res

    def _check_weekly_budget(self):
        """Check if this pool would exceed any weekly budget."""
        self.ensure_one()
        target_date = self.payment_date
        if not target_date or not self.line_ids:
            return

        budget_line = self._find_budget_line_for_date(target_date)
        if not budget_line:
            return  # No budget plan active, allow confirmation

        pool_amount = sum(line.total_qty * line.price_unit for line in self.line_ids)
        used = budget_line.amount_used
        limit_amt = budget_line.amount_limit
        total_after = used + pool_amount
        overage = total_after - limit_amt

        if overage > 0:
            budget_line.plan_id.message_post(
                body=_(
                    '<strong>Budget Exceeded Alert (Pool)</strong><br/>'
                    'Pool: <strong>%s</strong><br/>'
                    'User: %s<br/>'
                    'Week: %s<br/>'
                    'Budget: %s | Used: %s | Pool Amount: %s | Over by: %s'
                ) % (
                    self.name,
                    self.env.user.name,
                    budget_line.name,
                    '{:,.2f}'.format(limit_amt),
                    '{:,.2f}'.format(used),
                    '{:,.2f}'.format(pool_amount),
                    '{:,.2f}'.format(overage),
                ),
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )

            raise UserError(_(
                'Weekly Budget Exceeded! Cannot confirm or create RFQ for Procurement Pool.\n\n'
                'Week: %s\n'
                '  - Budget Limit: %s\n'
                '  - Already Used: %s\n'
                '  - This Pool (Estimate): %s\n'
                '  - Over by: %s'
            ) % (
                budget_line.name,
                '{:,.2f}'.format(limit_amt),
                '{:,.2f}'.format(used),
                '{:,.2f}'.format(pool_amount),
                '{:,.2f}'.format(overage),
            ))
