# -*- coding: utf-8 -*-
import logging
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


def _find_budget_allocations_for_date(env, target_date, company_id):
    if not target_date:
        return env['monthly.budget.allocation']
    return env['monthly.budget.allocation']._get_allocation(target_date, False, company_id)


class EmployeePurchaseRequisition(models.Model):
    _inherit = 'employee.purchase.requisition'

    @api.model
    def _get_default_department(self):
        if hasattr(self.env.user, 'employee_id') and self.env.user.employee_id:
            return self.env.user.employee_id.department_id
        if hasattr(self.env.company, 'default_department_id'):
            return self.env.company.default_department_id
        return False

    department_id = fields.Many2one(
        'hr.department',
        string='Department',
        store=True,
        default=_get_default_department,
    )

    payment_date = fields.Date(
        string='Expected Payment',
        compute='_compute_payment_date',
        store=True,
        readonly=False,
        help="Expected date of cash outflow. Default is Requisition Deadline + 30 days."
    )

    budget_check_result = fields.Html(
        string='Budget Check Result',
        compute='_compute_budget_check_result',
    )

    buz_budget_approval_id = fields.Many2one(
        'buz.budget.approval.request',
        string='Budget Approval Request',
        compute='_compute_budget_approval_id',
        store=False,
    )
    buz_budget_approval_state = fields.Selection(
        related='buz_budget_approval_id.state',
        string='Budget Approval Status',
    )
    budget_warning = fields.Boolean(
        string='Budget Warning',
        compute='_compute_budget_check_result'
    )
    is_budget_reserved = fields.Boolean(
        string='Budget is Reserved',
        compute='_compute_is_budget_reserved',
    )

    def _compute_is_budget_reserved(self):
        BudgetMove = self.env['budget.move'].sudo()
        for rec in self:
            rec.is_budget_reserved = bool(BudgetMove.search_count([
                ('source_model', '=', self._name),
                ('source_id', '=', rec.id),
                ('move_type', '=', 'reserved'),
            ]))

    def _compute_budget_approval_id(self):
        ApprovalReq = self.env['buz.budget.approval.request'].sudo()
        for rec in self:
            req = ApprovalReq.search([
                ('document_type', '=', 'pr'),
                ('ref_pr_id', '=', rec.id),
            ], limit=1, order='id desc')
            rec.buz_budget_approval_id = req

    @api.depends('requisition_deadline', 'request_date')
    def _compute_payment_date(self):
        for req in self:
            if req.payment_date:
                continue
            base_date = req.requisition_deadline or req.request_date or fields.Date.today()
            req.payment_date = base_date + timedelta(days=30)

    def _find_budget_allocation_for_date(self, target_date):
        dept = getattr(self, 'dept_id', False) or self.department_id
        allocations = self.env['monthly.budget.allocation']._get_allocation(
            target_date, dept, self.company_id
        )
        return allocations[:1] if allocations else False

    def write(self, vals):
        """Trigger budget reserved moves recompute when state or payment_date changes."""
        res = super().write(vals)
        if 'state' in vals or 'payment_date' in vals:
            self._update_budget_moves()
        return res

    def _clear_budget_moves(self):
        BudgetMove = self.env['budget.move'].sudo()
        for req in self:
            moves = BudgetMove.search([('source_model', '=', 'employee.purchase.requisition'), ('source_id', '=', req.id)])
            if moves:
                moves.unlink()

    def _update_budget_moves(self):
        self._clear_budget_moves()
        BudgetMove = self.env['budget.move'].sudo()
        BudgetAllocation = self.env['monthly.budget.allocation'].sudo()
        
        for req in self.filtered(lambda r: r.state != 'draft'):
            # Skip if linked to confirmed PO
            confirmed_pos = self.env['purchase.order'].sudo().search([
                ('state', 'in', ('purchase', 'done')),
                '|', ('requisition_order', '=', req.name),
                     ('pr_number', '=', req.name)
            ], limit=1)
            
            if confirmed_pos:
                continue
                
            budget_date = req.payment_date
            if not budget_date:
                continue
                
            for line in req.requisition_order_ids:
                amount = line.price_subtotal
                dists = BudgetMove.extract_analytic_distribution(line)
                for dist in dists:
                    dist_amount = amount * dist['percentage']
                    if dist_amount == 0: continue
                    
                    dept_obj = self.env['hr.department'].browse(dist['department_id']) if dist['department_id'] else False
                    bline = BudgetAllocation._get_allocation(
                        budget_date, dept_obj, req.company_id
                    )
                    if bline:
                        BudgetMove.create({
                            'name': f"{req.name} - {line.product_id.name or 'Line'}",
                            'allocation_id': bline.id,
                            'source_model': 'employee.purchase.requisition',
                            'source_id': req.id,
                            'source_line_id': line.id,
                            'analytic_account_id': dist['analytic_account_id'],
                            'department_id': dist['department_id'],
                            'amount': dist_amount,
                            'move_type': 'reserved',
                            'date': budget_date,
                        })

    @api.depends('requisition_order_ids.price_subtotal', 'payment_date')
    def _compute_budget_check_result(self):
        for req in self:
            target_date = req.payment_date
            if not target_date or not req.requisition_order_ids:
                req.budget_check_result = ''
                req.budget_warning = False
                continue

            budget_line = req._find_budget_allocation_for_date(target_date)
            if not budget_line:
                req.budget_check_result = _(
                    '<div class="alert alert-info">'
                    'No active monthly budget plan found for the expected payment date.'
                    '</div>'
                )
                req.budget_warning = False
                continue

            pr_amount = sum(req.requisition_order_ids.mapped('price_subtotal'))
            used = budget_line.amount_used
            reserved = budget_line.amount_reserved

            # Deduct this PR's own reservation to avoid double-counting
            own_reserved = sum(
                self.env['budget.move'].sudo().search([
                    ('source_model', '=', 'employee.purchase.requisition'),
                    ('source_id', '=', req.id),
                    ('allocation_id', '=', budget_line.id),
                    ('move_type', '=', 'reserved'),
                ]).mapped('amount')
            )
            other_reserved = max(0.0, reserved - own_reserved)

            limit_amt = budget_line.amount
            total_after = used + other_reserved + pr_amount
            remaining = limit_amt - total_after
            is_over = remaining < 0

            req.budget_warning = is_over

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
                '<p class="card-subtitle mb-2 text-muted"><strong>%s</strong> (%s - %s)</p>'
                '<table class="table table-sm table-borderless mb-0">'
                '<tr><td>%s</td><td class="text-end">%s</td></tr>'
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
                    budget_line.plan_id.name,
                    budget_line.department_id.name if budget_line.department_id else 'Base',
                    budget_line.date_from.strftime('%d %b %Y'),
                    budget_line.date_to.strftime('%d %b %Y'),
                    _('Monthly Budget'),
                    '{:,.2f}'.format(limit_amt),
                    _('Already Used (Confirmed POs)'),
                    '{:,.2f}'.format(used),
                    _('Already Reserved (Other PR/MR/RFQ)'),
                    '{:,.2f}'.format(other_reserved),
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

    def action_request_budget_approval(self):
        """Submit a budget approval request when budget is exceeded."""
        self.ensure_one()
        target_date = self.payment_date
        budget_line = self._find_budget_allocation_for_date(target_date) if target_date else False
        pr_amount = sum(self.requisition_order_ids.mapped('price_subtotal'))

        used = budget_line.amount_used if budget_line else 0.0
        reserved = budget_line.amount_reserved if budget_line else 0.0
        limit_amt = budget_line.amount if budget_line else 0.0

        # Deduct this PR's own reservation to avoid double-counting
        own_reserved = 0.0
        if budget_line:
            own_reserved = sum(
                self.env['budget.move'].sudo().search([
                    ('source_model', '=', 'employee.purchase.requisition'),
                    ('source_id', '=', self.id),
                    ('allocation_id', '=', budget_line.id),
                    ('move_type', '=', 'reserved'),
                ]).mapped('amount')
            )
        other_reserved = max(0.0, reserved - own_reserved)
        overage = max(0.0, used + other_reserved + pr_amount - limit_amt)

        return {
            'name': _('Request Budget Approval'),
            'type': 'ir.actions.act_window',
            'res_model': 'budget.request.reason.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_document_type': 'pr',
                'default_ref_id': self.id,
                'default_budget_line_id': False,
                'default_budget_allocation_id': budget_line.id if budget_line else False,
                'default_amount_requested': pr_amount,
                'default_amount_used': used,
                'default_amount_reserved': other_reserved,
                'default_amount_limit': limit_amt,
                'default_amount_overage': overage,
            }
        }

    def action_confirm_requisition(self):
        for req in self:
            req._check_monthly_budget()
        return super().action_confirm_requisition()

    def action_head_approval(self):
        for req in self:
            req._check_monthly_budget()
        return super().action_head_approval()

    def _check_monthly_budget(self):
        """Check if this PR would exceed any monthly budget."""
        self.ensure_one()
        target_date = self.payment_date
        if not target_date or not self.requisition_order_ids:
            return

        approved = self.env['buz.budget.approval.request'].sudo().search([
            ('document_type', '=', 'pr'),
            ('ref_pr_id', '=', self.id),
            ('state', '=', 'approved'),
        ], limit=1)
        if approved:
            return

        budget_line = self._find_budget_allocation_for_date(target_date)
        if not budget_line:
            raise UserError(_('No active monthly budget plan found for the expected payment date.'))

        pr_amount = sum(self.requisition_order_ids.mapped('price_subtotal'))
        used = budget_line.amount_used
        reserved = budget_line.amount_reserved

        # Deduct this PR's own reservation to avoid double-counting
        own_reserved = sum(
            self.env['budget.move'].sudo().search([
                ('source_model', '=', 'employee.purchase.requisition'),
                ('source_id', '=', self.id),
                ('allocation_id', '=', budget_line.id),
                ('move_type', '=', 'reserved'),
            ]).mapped('amount')
        )
        other_reserved = max(0.0, reserved - own_reserved)

        limit_amt = budget_line.amount
        total_after = used + other_reserved + pr_amount
        overage = total_after - limit_amt

        if overage > 0:
            budget_line.plan_id.message_post(
                body=_(
                    '<strong>Budget Exceeded Alert (PR)</strong><br/>'
                    'PR: <strong>%s</strong><br/>'
                    'User: %s<br/>'
                    'Month: %s (%s)<br/>'
                    'Budget: %s | Used: %s | Reserved: %s | PR Amount: %s | Over by: %s'
                ) % (
                    self.name,
                    self.env.user.name,
                    budget_line.plan_id.name,
                    budget_line.department_id.name if budget_line.department_id else 'Base',
                    '{:,.2f}'.format(limit_amt),
                    '{:,.2f}'.format(used),
                    '{:,.2f}'.format(other_reserved),
                    '{:,.2f}'.format(pr_amount),
                    '{:,.2f}'.format(overage),
                ),
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )

            raise UserError(_(
                'Monthly Budget Exceeded! Cannot approve Purchase Requisition.\n\n'
                'Month: %s (%s)\n'
                '  - Budget Limit: %s\n'
                '  - Already Used: %s\n'
                '  - Already Reserved: %s\n'
                '  - This PR: %s\n'
                '  - Over by: %s\n\n'
                'Please click "ขอเพิ่มงบประมาณ" to submit a Budget Approval Request.'
            ) % (
                budget_line.plan_id.name,
                budget_line.department_id.name if budget_line.department_id else 'Base',
                '{:,.2f}'.format(limit_amt),
                '{:,.2f}'.format(used),
                '{:,.2f}'.format(other_reserved),
                '{:,.2f}'.format(pr_amount),
                '{:,.2f}'.format(overage),
            ))
