# -*- coding: utf-8 -*-
import logging
from collections import defaultdict
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    payment_date = fields.Date(
        string='Expected Payment',
        compute='_compute_payment_date',
        store=True,
        readonly=False,
        help="Expected date of cash outflow. Default is calculated based on payment terms or Order Date + 30 days."
    )

    billed_amount = fields.Float(
        string='Billed Amount',
        compute='_compute_billed_amount',
        store=True,
    )
    remaining_to_bill = fields.Float(
        string='Remaining to Bill',
        compute='_compute_billed_amount',
        store=True,
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

    def _compute_budget_approval_id(self):
        ApprovalReq = self.env['buz.budget.approval.request'].sudo()
        for rec in self:
            req = ApprovalReq.search([
                ('document_type', '=', 'po'),
                ('ref_po_id', '=', rec.id),
            ], limit=1, order='id desc')
            rec.buz_budget_approval_id = req

    @api.depends('invoice_ids.state', 'invoice_ids.amount_total', 'amount_total')
    def _compute_billed_amount(self):
        for order in self:
            posted_bills = order.invoice_ids.filtered(
                lambda m: m.move_type == 'in_invoice' and m.state == 'posted'
            )
            # Use invoice lines related to this purchase order to calculate the actual billed amount against this PO
            # Sometimes billed_amount is calculated directly by sum(posted_bills.mapped('amount_total'))
            # but standard odoo approach might be better. Let's stick to simple sum for now as we just need total.
            # But wait, a bill could cover multiple POs.
            amount = 0.0
            for bill in posted_bills:
                # Calculate proportion of this bill that belongs to this PO
                for line in bill.invoice_line_ids:
                    if line.purchase_line_id and line.purchase_line_id.order_id.id == order.id:
                        amount += line.price_total
            
            # Simple approach if standard invoice_ids contains only bills for this PO
            order.billed_amount = sum(posted_bills.mapped('amount_total')) if not amount else amount
            order.remaining_to_bill = max(0.0, order.amount_total - order.billed_amount)

    # Budget info fields (computed on demand via button)
    budget_check_result = fields.Html(
        string='Budget Check Result',
        compute='_compute_budget_check_result',
    )
    budget_warning = fields.Boolean(
        string='Budget Warning',
        compute='_compute_budget_check_result',
    )

    @api.depends('date_order', 'payment_term_id', 'partner_id')
    def _compute_payment_date(self):
        for order in self:
            if order.payment_date:  # Keep manual override
                continue
            
            base_date = fields.Date.to_date(order.date_order) or fields.Date.context_today(order)
            
            if order.payment_term_id:
                # Use the first line of the payment term to estimate
                pterm = order.payment_term_id
                if pterm.line_ids:
                    line = pterm.line_ids[0]
                    if line.delay_type == 'days_after_end_of_month':
                        # Simplification for estimation
                        order.payment_date = base_date + timedelta(days=line.nb_days + 30)
                    else:
                        order.payment_date = base_date + timedelta(days=line.nb_days)
                else:
                    order.payment_date = base_date + timedelta(days=30)
            else:
                order.payment_date = base_date + timedelta(days=30)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('payment_date'):
                # 1. Check Procurement Pool
                if vals.get('procurement_pool_id'):
                    pool = self.env['procurement.pool'].browse(vals['procurement_pool_id'])
                    if pool.payment_date:
                        vals['payment_date'] = pool.payment_date
                
                # 2. Check Material Requisition (MR)
                elif vals.get('material_requisition_id'):
                    mr = self.env['material.requisition'].browse(vals['material_requisition_id'])
                    if mr.payment_date:
                        vals['payment_date'] = mr.payment_date
                
                # 3. Check Purchase Requisition (PR)
                elif vals.get('requisition_order'):
                    pr = self.env['employee.purchase.requisition'].search([('name', '=', vals['requisition_order'])], limit=1)
                    if pr and pr.payment_date:
                        vals['payment_date'] = pr.payment_date
                        
        return super().create(vals_list)

    def write(self, vals):
        """Trigger budget reserved recompute when PO state or payment_date changes."""
        old_data = {rec.id: {'state': rec.state, 'payment_date': rec.payment_date} for rec in self}
        result = super().write(vals)
        
        if 'state' in vals or 'payment_date' in vals:
            BudgetLine = self.env['weekly.budget.line'].sudo()
            for rec in self:
                # Recompute for both old and new dates to ensure totals are correct
                dates_to_update = set()
                if old_data[rec.id]['payment_date']:
                    dates_to_update.add(old_data[rec.id]['payment_date'])
                if rec.payment_date:
                    dates_to_update.add(rec.payment_date)
                
                for target_date in dates_to_update:
                    budget_lines = BudgetLine.search([
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

    def _get_weekly_budget_lines_for_po(self):
        """Return dict: {budget_line: po_amount} based on PO Payment Date."""
        self.ensure_one()
        result = defaultdict(float)

        target_date = self.payment_date or fields.Date.to_date(self.date_order)
        if not target_date:
            return result

        budget_line = self._find_budget_line_for_date(target_date)
        if budget_line:
            result[budget_line] = self.amount_total

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

    @api.depends('amount_total', 'payment_date', 'state')
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
                    'No active weekly budget plan found for the expected payment date.'
                    '</div>'
                )
                order.budget_warning = False
                continue

            html_parts = []
            has_warning = False

            for budget_line, po_amount in week_amounts.items():
                # Get the actual used and reserved from the system
                used = budget_line.amount_used
                reserved = budget_line.amount_reserved
                limit_amt = budget_line.amount_limit

                po_unbilled = order.remaining_to_bill if order.state in ['purchase', 'done'] else order.amount_total
                other_reserved = max(0.0, reserved - po_unbilled)

                total_after = used + reserved
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
                    '<tr><td>%s</td><td class="text-end text-primary">%s</td></tr>'
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
                        _('Used (Billed)'),
                        '{:,.2f}'.format(used),
                        _('Other Reserved (PR/MR/PO)'),
                        '{:,.2f}'.format(other_reserved),
                        _('This PO (Unbilled)'),
                        '{:,.2f}'.format(po_unbilled),
                        _('Projected Total'),
                        '{:,.2f}'.format(total_after),
                        _('Remaining Available'),
                        status_class,
                        '{:,.2f}'.format(remaining),
                        status_text,
                    )
                )

            order.budget_check_result = ''.join(html_parts)
            order.budget_warning = has_warning

    def _get_po_amount_in_budget_line(self, po, budget_line):
        """Deprecated: Logic is now handled by observing the budget line natively."""
        return 0.0

    def action_check_budget(self):
        """Button action to trigger budget check recomputation."""
        self.ensure_one()
        # Force recompute
        self._compute_budget_check_result()
        return True

    def action_request_budget_approval(self):
        """Submit a budget approval request when budget is exceeded."""
        self.ensure_one()
        week_amounts = self._get_weekly_budget_lines_for_po()
        budget_line = next(iter(week_amounts), False)
        po_amount = week_amounts.get(budget_line, self.amount_total) if budget_line else self.amount_total

        used = budget_line.amount_used if budget_line else 0.0
        reserved = budget_line.amount_reserved if budget_line else 0.0
        limit_amt = budget_line.amount_limit if budget_line else 0.0
        overage = max(0.0, used + reserved - limit_amt)

        ApprovalReq = self.env['buz.budget.approval.request']

        return {
            'name': _('Request Budget Approval'),
            'type': 'ir.actions.act_window',
            'res_model': 'budget.request.reason.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_document_type': 'po',
                'default_ref_id': self.id,
                'default_budget_line_id': budget_line.id if budget_line else False,
                'default_amount_requested': po_amount,
                'default_amount_used': used,
                'default_amount_reserved': reserved,
                'default_amount_limit': limit_amt,
                'default_amount_overage': overage,
            }
        }

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

        ApprovalReq = self.env['buz.budget.approval.request'].sudo()

        # 1. Check if an approved budget request exists for THIS PO
        approved_po = ApprovalReq.search([
            ('document_type', '=', 'po'),
            ('ref_po_id', '=', self.id),
            ('state', '=', 'approved'),
        ], limit=1)
        if approved_po:
            return  # Bypass

        # 2. Check if approved from source PR
        if self.requisition_order:
            pr = self.env['employee.purchase.requisition'].search([('name', '=', self.requisition_order)], limit=1)
            if pr:
                approved_pr = ApprovalReq.search([
                    ('document_type', '=', 'pr'),
                    ('ref_pr_id', '=', pr.id),
                    ('state', '=', 'approved'),
                ], limit=1)
                if approved_pr:
                    return

        # 3. Check if approved from source MR
        if getattr(self, 'material_requisition_id', False):
            approved_mr = ApprovalReq.search([
                ('document_type', '=', 'mr'),
                ('ref_mr_id', '=', self.material_requisition_id.id),
                ('state', '=', 'approved'),
            ], limit=1)
            if approved_mr:
                return

        week_amounts = self._get_weekly_budget_lines_for_po()

        if not week_amounts:
            return  # No budget plan active, allow confirmation

        violations = []
        for budget_line, po_amount in week_amounts.items():
            used = budget_line.amount_used
            reserved = budget_line.amount_reserved
            limit_amt = budget_line.amount_limit
            total_after = used + reserved
            overage = total_after - limit_amt

            if overage > 0:
                violations.append({
                    'line': budget_line,
                    'limit': limit_amt,
                    'used': used,
                    'reserved': reserved,
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
                  '  - Used (Billed): %s\n'
                  '  - Reserved (Unbilled/PR/MR): %s\n'
                  '  - Over by: %s\n') % (
                    v['line'].name,
                    '{:,.2f}'.format(v['limit']),
                    '{:,.2f}'.format(v['used']),
                    '{:,.2f}'.format(v['reserved']),
                    '{:,.2f}'.format(v['overage']),
                )
            )

        # append guidance message
        msg_parts.append(
            _('\nPlease click "ขอเพิ่มงบประมาณ" button to submit a Budget Approval Request.')
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
                    'Budget: %s | Used: %s | Reserved: %s | Over by: %s'
                ) % (
                    self.name,
                    self.env.user.name,
                    v['line'].name,
                    '{:,.2f}'.format(v['limit']),
                    '{:,.2f}'.format(v['used']),
                    '{:,.2f}'.format(v['reserved']),
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
                'reserved': '{:,.2f}'.format(v['reserved']),
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
