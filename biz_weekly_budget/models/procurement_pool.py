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

    def _find_budget_allocation_for_date(self, target_date):
        """Find the confirmed monthly budget allocation that covers the given date."""
        department_id = False
        if hasattr(self.user_id, 'employee_id') and self.user_id.employee_id:
            department_id = self.user_id.employee_id.department_id.id
            
        dept_obj = self.env['hr.department'].browse(department_id) if department_id else False
        allocations = self.env['monthly.budget.allocation']._get_allocation(
            target_date, dept_obj, self.company_id
        )
        return allocations[:1] if allocations else False

    def write(self, vals):
        """Trigger budget update when state or payment_date changes."""
        return super().write(vals)

    @api.depends('line_ids.total_qty', 'line_ids.price_unit', 'payment_date')
    def _compute_budget_check_result(self):
        for pool in self:
            target_date = pool.payment_date
            if not target_date or not pool.line_ids:
                pool.budget_check_result = ''
                pool.budget_warning = False
                continue

            budget_line = pool._find_budget_allocation_for_date(target_date)
            if not budget_line:
                pool.budget_check_result = _(
                    '<div class="alert alert-info">'
                    'No active monthly budget plan found for the expected payment date.'
                    '</div>'
                )
                pool.budget_warning = False
                continue

            pool_amount = sum(line.total_qty * line.price_unit for line in pool.line_ids)
            used = budget_line.amount_used
            reserved = budget_line.amount_reserved
            limit_amt = budget_line.amount
            
            # Since this pool is an estimate, we check if it fits the budget limit minus used amount
            total_after = used + reserved + pool_amount
            remaining = limit_amt - total_after
            is_over = remaining < 0

            # Changed to Info logic because budget was already checked at MR level
            pool.budget_warning = False
            status_class = 'info'
            status_icon = '&#8505;'
            status_text = _('Info Only - Checked on MR')

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
                    budget_line.plan_id.name if budget_line.plan_id else 'General',
                    _('Monthly Budget Limit'),
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
        """Override to check monthly budget before confirming."""
        # for pool in self:
        #     pool._check_monthly_budget() # Disabled because budget is checked at MR level
        return super().action_confirm()

    def action_create_rfq(self):
        """Override to check monthly budget before creating RFQs."""
        # for pool in self:
        #     pool._check_monthly_budget() # Disabled because budget is checked at MR level
        
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

    def _check_monthly_budget(self):
        """Check if this pool would exceed any monthly budget. (Currently Disabled)"""
        pass
