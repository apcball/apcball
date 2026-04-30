# -*- coding: utf-8 -*-
import logging
from collections import defaultdict
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    department_id = fields.Many2one(
        'hr.department',
        string='Department',
        store=True,
    )

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    # department_id is defined in buz_po_portal, no redefinition needed here.
    # Department inheritance from source documents is handled in create().

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
                lambda m: m.move_type == 'in_invoice' and m.state in ('draft', 'posted')
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
    is_budget_reserved = fields.Boolean(
        string='Budget is Reserved',
        compute='_compute_is_budget_reserved',
    )

    def _compute_is_budget_reserved(self):
        BudgetMove = self.env['budget.move'].sudo()
        for rec in self:
            po_reserved = bool(BudgetMove.search_count([
                ('source_model', '=', self._name),
                ('source_id', '=', rec.id),
                ('move_type', '=', 'reserved'),
            ]))
            
            if po_reserved:
                rec.is_budget_reserved = True
                continue
                
            # If PO is still draft/to approve, check if source doc is holding the budget on its behalf
            if rec.state in ('draft', 'sent', 'to approve'):
                pr_name = getattr(rec, 'requisition_order', False) or getattr(rec, 'pr_number', False)
                if pr_name:
                    pr = self.env['employee.purchase.requisition'].sudo().search([('name', '=', pr_name)], limit=1)
                    if pr and getattr(pr, 'is_budget_reserved', False):
                        rec.is_budget_reserved = True
                        continue
                
                mr_linked = getattr(rec, 'material_requisition_id', False)
                if not mr_linked and getattr(rec, 'origin', False):
                    mr_linked = self.env['material.requisition'].sudo().search([('name', '=', rec.origin)], limit=1)
                if mr_linked and getattr(mr_linked, 'is_budget_reserved', False):
                    rec.is_budget_reserved = True
                    continue
                    
            rec.is_budget_reserved = False

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
            # =============================================
            # Department Inheritance from Source Document
            # Priority: PR > MR > Pool > current user
            # =============================================
            if not vals.get('department_id'):
                # 1. From Purchase Requisition (PR)
                pr_name = vals.get('requisition_order') or vals.get('pr_number')
                if pr_name:
                    pr = self.env['employee.purchase.requisition'].sudo().search(
                        [('name', '=', pr_name)], limit=1)
                    if pr:
                        src_dept = pr.dept_id or pr.department_id
                        if src_dept:
                            vals['department_id'] = src_dept.id

                # 2. From Material Requisition (MR)
                if not vals.get('department_id') and vals.get('material_requisition_id'):
                    mr = self.env['material.requisition'].sudo().browse(
                        vals['material_requisition_id'])
                    if mr.exists() and mr.department_id:
                        vals['department_id'] = mr.department_id.id

                # 3. From Procurement Pool (first MR department)
                if not vals.get('department_id') and vals.get('procurement_pool_id'):
                    pool = self.env['procurement.pool'].sudo().browse(
                        vals['procurement_pool_id'])
                    if pool.exists():
                        for pline in pool.line_ids:
                            if pline.department_id:
                                vals['department_id'] = pline.department_id.id
                                break

                # 4. Fallback to current user's department
                if not vals.get('department_id'):
                    emp = self.env.user.employee_id
                    if emp and emp.department_id:
                        vals['department_id'] = emp.department_id.id

            # =============================================
            # Payment Date Inheritance from Source Document
            # =============================================
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
        """Trigger budget reserved moves update when state or payment_date changes."""
        res = super().write(vals)
        if 'state' in vals or 'payment_date' in vals or 'qty_invoiced' in vals or 'order_line' in vals:
            self._update_budget_moves()
        return res

    def _clear_budget_moves(self):
        BudgetMove = self.env['budget.move'].sudo()
        for po in self:
            moves = BudgetMove.search([('source_model', '=', 'purchase.order'), ('source_id', '=', po.id)])
            if moves:
                moves.unlink()

    def _trigger_linked_docs_recompute(self):
        """Recompute PR/MR budget moves to clear their reservation if PO takes over."""
        for po in self:
            if getattr(po, 'requisition_order', False) or getattr(po, 'pr_number', False):
                name = getattr(po, 'requisition_order', False) or getattr(po, 'pr_number', False)
                if name:
                    pr = self.env['employee.purchase.requisition'].sudo().search([('name', '=', name)], limit=1)
                    if pr: pr._update_budget_moves()
            if getattr(po, 'material_requisition_id', False):
                po.material_requisition_id._update_budget_moves()
            if po.origin:
                mr = self.env['material.requisition'].sudo().search([('name', '=', po.origin)], limit=1)
                if mr: mr._update_budget_moves()
            
            # Update MR based on PO lines (e.g., from Procurement Pool)
            mr_lines_linked = getattr(po.order_line, 'material_requisition_line_id', False)
            if mr_lines_linked:
                mrs = mr_lines_linked.mapped('requisition_id')
                for mr in mrs:
                    mr._update_budget_moves()

    def _update_budget_moves(self):
        """Rebuild 'reserved' budget.move entries for this PO.

        For confirmed POs (state purchase/done), only the *unbilled* quantity is
        reserved — lines that already have a draft or posted vendor bill are counted
        as 'used' (via the bill's own budget.move) and are excluded from the
        reservation so we don't double-count.

        This method is called both when the PO changes state AND when a linked bill
        is created/cancelled, ensuring the reserved amount always equals only the
        amount not yet invoiced.
        """
        # Recursion guard: avoid PO → bill → PO loops
        if self.env.context.get('_budget_po_updating'):
            return
        self = self.with_context(_budget_po_updating=True)

        self._clear_budget_moves()
        self._trigger_linked_docs_recompute()

        BudgetMove = self.env['budget.move'].sudo()
        BudgetAllocation = self.env['monthly.budget.allocation'].sudo()
        
        for po in self.filtered(lambda p: p.state not in ('cancel',)):
            budget_date = po.payment_date or fields.Date.to_date(po.date_order)
            if not budget_date:
                continue
                
            if po.state in ('draft', 'sent', 'to approve'):
                pr_name = getattr(po, 'requisition_order', False) or getattr(po, 'pr_number', False)
                mr1 = getattr(po, 'material_requisition_id', False)
                pr = self.env['employee.purchase.requisition'].sudo().search([('name', '=', pr_name)], limit=1) if pr_name else False
                mr2 = self.env['material.requisition'].sudo().search([('name', '=', po.origin)], limit=1) if po.origin else False
                
                # Check if generated from MR via Pool (PO lines linked)
                mr_line_linked = getattr(po.order_line, 'material_requisition_line_id', False)
                
                if pr or mr1 or mr2 or mr_line_linked:
                    continue
                    
            for line in po.order_line:
                if line.display_type not in (False, 'product', ''):
                    continue
                    
                amount = line.price_subtotal
                if po.state in ('purchase', 'done'):
                    qty_billed = 0.0
                    for inv_line in line.invoice_lines:
                        if inv_line.move_id.state in ('draft', 'posted'):
                            if inv_line.move_id.move_type == 'in_invoice':
                                qty_billed += inv_line.quantity
                            elif inv_line.move_id.move_type == 'in_refund':
                                qty_billed -= inv_line.quantity
                    qty_unbilled = line.product_qty - qty_billed
                    if qty_unbilled <= 0:
                        continue
                    amount = (qty_unbilled / line.product_qty) * line.price_subtotal if line.product_qty else 0
                    
                if amount <= 0:
                    continue
                    
                dists = BudgetMove.extract_analytic_distribution(line)
                for dist in dists:
                    dist_amount = amount * dist['percentage']
                    if dist_amount == 0: continue
                    
                    dept_obj = self.env['hr.department'].browse(dist['department_id']) if dist['department_id'] else False
                    bline = BudgetAllocation._get_allocation(
                        budget_date, dept_obj, po.company_id
                    )
                    if bline:
                        BudgetMove.create({
                            'name': f"{po.name} - {line.name or 'Line'}",
                            'allocation_id': bline.id,
                            'source_model': 'purchase.order',
                            'source_id': po.id,
                            'source_line_id': line.id,
                            'analytic_account_id': dist['analytic_account_id'],
                            'department_id': dist['department_id'],
                            'amount': dist_amount,
                            'move_type': 'reserved',
                            'date': budget_date,
                        })

    def _get_monthly_budget_allocation_for_po(self):
        """Return dict: {budget_allocation: po_amount} based on PO lines' departments and Payment Date."""
        self.ensure_one()
        result = defaultdict(float)

        target_date = self.payment_date or fields.Date.to_date(self.date_order)
        if not target_date:
            return result

        BudgetMove = self.env['budget.move']
        for line in self.order_line:
            if line.display_type not in (False, 'product', ''):
                continue
            
            amount = line.price_subtotal
            if amount <= 0:
                continue
                
            dists = BudgetMove.extract_analytic_distribution(line)
            for dist in dists:
                dist_amount = amount * dist['percentage']
                if dist_amount == 0: continue
                
                budget_line = self._find_budget_allocation_for_date(target_date, department_id=dist['department_id'])
                if budget_line:
                    result[budget_line] += dist_amount
                    
        if not result and self.amount_untaxed:
            # Fallback
            budget_line = self._find_budget_allocation_for_date(target_date, department_id=self.department_id.id)
            if budget_line:
                result[budget_line] = self.amount_untaxed

        return result

    def _find_budget_allocation_for_date(self, target_date, department_id=False):
        """Find the confirmed budget allocation that covers the given date."""
        if not department_id:
            dept = getattr(self, 'dept_id', False) or getattr(self, 'department_id', False)
            department_id = dept.id if hasattr(dept, 'id') else (dept or False)
            
        dept_obj = self.env['hr.department'].browse(department_id) if department_id else False
        allocations = self.env['monthly.budget.allocation']._get_allocation(
            target_date, dept_obj, self.company_id
        )
        return allocations[:1] if allocations else False

    @api.depends('amount_total', 'payment_date', 'state')
    def _compute_budget_check_result(self):
        for order in self:
            if not order.order_line:
                order.budget_check_result = ''
                order.budget_warning = False
                continue

            month_amounts = order._get_monthly_budget_allocation_for_po()
            if not month_amounts:
                order.budget_check_result = _(
                    '<div class="alert alert-info">'
                    'No active monthly budget plan found for the expected payment date.'
                    '</div>'
                )
                order.budget_warning = False
                continue

            html_parts = []
            has_warning = False

            for budget_line, po_amount in month_amounts.items():
                used = budget_line.amount_used
                reserved = budget_line.amount_reserved
                limit_amt = budget_line.amount

                po_unbilled = po_amount
                if order.state in ['purchase', 'done']:
                    ratio = order.remaining_to_bill / order.amount_total if order.amount_total else 0
                    po_unbilled = po_amount * ratio
                    
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
                    '<p class="card-subtitle mb-2 text-muted"><strong>%s</strong> (%s - %s)</p>'
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
                        budget_line.plan_id.name,
                        budget_line.department_id.name if budget_line.department_id else 'Base',
                        budget_line.date_from.strftime('%d %b %Y'),
                        budget_line.date_to.strftime('%d %b %Y'),
                        _('Monthly Budget'),
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
        self.ensure_one()
        month_amounts = self._get_monthly_budget_allocation_for_po()
        budget_line = next(iter(month_amounts), False)
        po_amount = month_amounts.get(budget_line, self.amount_total) if budget_line else self.amount_total

        used = budget_line.amount_used if budget_line else 0.0
        reserved = budget_line.amount_reserved if budget_line else 0.0
        limit_amt = budget_line.amount if budget_line else 0.0
        overage = max(0.0, used + reserved - limit_amt)

        return {
            'name': _('Request Budget Approval'),
            'type': 'ir.actions.act_window',
            'res_model': 'budget.request.reason.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_document_type': 'po',
                'default_ref_id': self.id,
                'default_budget_line_id': False, # Removed weekly relation
                'default_budget_allocation_id': budget_line.id if budget_line else False,
                'default_amount_requested': po_amount,
                'default_amount_used': used,
                'default_amount_reserved': reserved,
                'default_amount_limit': limit_amt,
                'default_amount_overage': overage,
            }
        }

    def action_submit_for_review(self):
        """Override to check monthly budget before sending for review."""
        for order in self:
            order._check_monthly_budget()
        return super().action_submit_for_review()

    def button_confirm(self):
        """Override to check monthly budget before confirming."""
        for order in self:
            order._check_monthly_budget()
        return super().button_confirm()

    def button_cancel(self):
        """Override to handle source document state on PO cancellation.

        Instead of blindly cascading cancel:
        - PR: only cancel if NO other active POs reference the same PR.
        - MR: return to 'approved' (not cancelled) if no other active POs
          reference the same MR, allowing re-procurement.
        """
        res = super().button_cancel()
        for po in self:
            # --- PR cascade ---
            pr_name = getattr(po, 'requisition_order', False) or getattr(po, 'pr_number', False)
            if pr_name:
                pr = self.env['employee.purchase.requisition'].sudo().search(
                    [('name', '=', pr_name)], limit=1)
                if pr and pr.state != 'cancelled':
                    other_active_pos = self.env['purchase.order'].sudo().search([
                        ('id', '!=', po.id),
                        '|', ('requisition_order', '=', pr_name),
                             ('pr_number', '=', pr_name),
                        ('state', 'not in', ('cancel',)),
                    ], limit=1)
                    if not other_active_pos:
                        pr.write({
                            'state': 'cancelled',
                            'reject_date': fields.Date.today(),
                        })
                        pr.message_post(
                            body=_('PR cancelled — last linked PO %s was cancelled.') % po.name,
                            message_type='notification',
                            subtype_xmlid='mail.mt_note',
                        )

            # --- MR cascade ---
            mr_linked = getattr(po, 'material_requisition_id', False)
            if not mr_linked and getattr(po, 'origin', False):
                mr_linked = self.env['material.requisition'].sudo().search(
                    [('name', '=', po.origin)], limit=1)

            if mr_linked and mr_linked.state not in ('draft', 'cancelled', 'cancel'):
                other_active_pos = self.env['purchase.order'].sudo().search([
                    ('id', '!=', po.id),
                    '|', ('material_requisition_id', '=', mr_linked.id),
                         ('origin', '=', mr_linked.name),
                    ('state', 'not in', ('cancel',)),
                ], limit=1)
                if not other_active_pos:
                    # Return MR to approved — allow re-procurement
                    mr_linked.write({'state': 'approved'})
                    mr_linked.message_post(
                        body=_('MR returned to Approved — PO %s was cancelled. '
                               'You may re-issue a Purchase Order.') % po.name,
                        message_type='notification',
                        subtype_xmlid='mail.mt_note',
                    )
                    # Recompute MR budget moves
                    if hasattr(mr_linked, '_update_budget_moves'):
                        mr_linked._update_budget_moves()
        return res

    def _check_monthly_budget(self):
        """Check if confirming this PO would exceed any monthly budget."""
        self.ensure_one()

        ApprovalReq = self.env['buz.budget.approval.request'].sudo()

        approved_po = ApprovalReq.search([
            ('document_type', '=', 'po'),
            ('ref_po_id', '=', self.id),
            ('state', '=', 'approved'),
        ], limit=1)
        if approved_po:
            return

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

        if getattr(self, 'material_requisition_id', False):
            approved_mr = ApprovalReq.search([
                ('document_type', '=', 'mr'),
                ('ref_mr_id', '=', self.material_requisition_id.id),
                ('state', '=', 'approved'),
            ], limit=1)
            if approved_mr:
                return

        month_amounts = self._get_monthly_budget_allocation_for_po()

        if not month_amounts:
            raise UserError(_('No active monthly budget plan found for the expected payment date.'))

        violations = []
        for budget_line, po_amount in month_amounts.items():
            used = budget_line.amount_used
            reserved = budget_line.amount_reserved
            limit_amt = budget_line.amount
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
        """Block PO confirmation or warn based on configuration."""
        self.ensure_one()
        control_type = self.env.company.budget_control_type if hasattr(self.env.company, 'budget_control_type') else 'hard'

        # Build error message
        msg_parts = [_('Monthly Budget Exceeded! Cannot proceed with Purchase Order.\n')]
        for v in violations:
            msg_parts.append(
                _('Month: %s (%s)\n'
                  '  - Budget Limit: %s\n'
                  '  - Used (Billed): %s\n'
                  '  - Reserved (Unbilled/PR/MR): %s\n'
                  '  - Over by: %s\n') % (
                    v['line'].plan_id.name,
                    v['line'].department_id.name if v['line'].department_id else 'Base',
                    '{:,.2f}'.format(v['limit']),
                    '{:,.2f}'.format(v['used']),
                    '{:,.2f}'.format(v['reserved']),
                    '{:,.2f}'.format(v['overage']),
                )
            )

        msg_parts.append(_('\nPlease click "ขอเพิ่มงบประมาณ" button to submit a Budget Approval Request.'))

        self._send_budget_exceeded_notification(violations)

        for v in violations:
            plan = v['line'].plan_id
            plan.message_post(
                body=_(
                    '<strong>Budget Exceeded Alert</strong><br/>'
                    'PO: <strong>%s</strong><br/>'
                    'User: %s<br/>'
                    'Month: %s (%s)<br/>'
                    'Budget: %s | Used: %s | Reserved: %s | Over by: %s'
                ) % (
                    self.name,
                    self.env.user.name,
                    v['line'].plan_id.name,
                    v['line'].department_id.name if v['line'].department_id else 'Base',
                    '{:,.2f}'.format(v['limit']),
                    '{:,.2f}'.format(v['used']),
                    '{:,.2f}'.format(v['reserved']),
                    '{:,.2f}'.format(v['overage']),
                ),
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )

        if control_type == 'hard':
            raise UserError('\n'.join(msg_parts))
        else:
            self.message_post(body=_('<strong>Budget Warning:</strong><br/>') + '<br/>'.join(msg_parts).replace('\n', '<br/>'))

    def _send_budget_exceeded_notification(self, violations):
        template = self.env.ref(
            'biz_weekly_budget.mail_template_budget_exceeded',
            raise_if_not_found=False,
        )
        if not template:
            return

        notify_users = self.env['res.users']
        for v in violations:
            notify_users |= v['line'].plan_id.notify_user_ids

        if not notify_users:
            return

        violation_details = []
        for v in violations:
            violation_details.append({
                'week_name': v['line'].plan_id.name, # Use plan name instead of week
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
                pass
