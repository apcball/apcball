# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools.misc import clean_context


class SaleOrder(models.Model):
    _inherit = 'sale.order'
    
    # Approval fields
    approval_state = fields.Selection([
        ('not_required', 'Not Required'),
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string='Approval Status', default='not_required', copy=False)
    
    # Approval date — timestamp when margin was last approved
    margin_approval_date = fields.Datetime(
        string='Margin Approval Date',
        copy=False,
        readonly=True,
    )

    # Rewrite tracking field
    rewrite_count = fields.Integer(
        string='Rewrite Version',
        default=0,
        copy=False,
        help='Number of times this quotation has been rewritten after customer rejection'
    )

    # Confirm flow fields
    confirm_flow_state = fields.Selection([
        ('draft', 'Quotation'),
        ('confirm_to_so', 'Confirm To SO'),
        ('sale', 'Sales Order'),
    ], string='Confirm Flow State', default='draft', copy=False)
    
    margin_percentage = fields.Float(
        string='Margin %', 
        compute='_compute_margin_percentage', 
        store=True
    )
    margin_rule_id = fields.Many2one(
        'margin.approval.rule', 
        string='Applied Margin Rule', 
        compute='_compute_margin_rule', 
        store=True
    )
    margin_rule_line_id = fields.Many2one(
        'margin.approval.rule.line',
        string='Applied Margin Line',
        compute='_compute_margin_rule',
        store=True
    )
    margin_approval_user_ids = fields.Many2many(
        'res.users',
        'sale_order_margin_approver_rel',
        'order_id',
        'user_id', 
        string='Margin Approvers', 
        compute='_compute_margin_rule', 
        store=True
    )
    approval_type = fields.Selection(
        related='margin_rule_line_id.approval_type',
        string='Approval Type',
        readonly=True
    )
    approved_user_ids = fields.Many2many(
        'res.users',
        'sale_order_approved_user_rel',
        'order_id',
        'user_id',
        string='Users Who Approved',
        copy=False
    )
    can_current_user_approve = fields.Boolean(
        string='Can Current User Approve',
        compute='_compute_can_current_user_approve',
        search='_search_can_current_user_approve',
        help='Check if current user can approve this order'
    )
    
    def _compute_can_current_user_approve(self):
        """Check if current user can approve each order"""
        for order in self:
            order.can_current_user_approve = order._can_approve_margin()
    
    def _search_can_current_user_approve(self, operator, value):
        """Search method for can_current_user_approve field
        
        Shows orders based on user's role:
        - Admin group (group_margin_approval_admin): sees ALL pending orders
        - Regular approvers: see only orders within their authorized margin ranges
        """
        current_user = self.env.user
        
        # Admin group can see ALL pending orders (not restricted by margin range)
        if current_user.has_group('buz_margin_approval.group_margin_approval_admin'):
            if (operator == '=' and value) or (operator == '!=' and not value):
                return [('approval_state', '=', 'pending')]
            else:
                return [('id', '=', False)]
        
        # Regular approvers: only show orders where user is specifically in margin_approval_user_ids
        # (which is calculated based on the order's margin and matching rule line)
        if (operator == '=' and value) or (operator == '!=' and not value):
            return [
                ('approval_state', '=', 'pending'),
                ('margin_approval_user_ids', 'in', current_user.id)
            ]
        else:
            return [
                '|',
                ('approval_state', '!=', 'pending'),
                ('margin_approval_user_ids', 'not in', current_user.id)
            ]
    
    @api.depends('margin', 'amount_untaxed')
    def _compute_margin_percentage(self):
        for order in self:
            if order.amount_untaxed:
                # Use margin from sale_margin module
                order.margin_percentage = (order.margin / order.amount_untaxed) * 100.0
            else:
                order.margin_percentage = 0.0
    
    @api.depends('user_id', 'company_id', 'margin_percentage')
    def _compute_margin_rule(self):
        for order in self:
            rule = self.env['margin.approval.rule'].get_applicable_rule_for_user(
                order.user_id.id, 
                order.company_id.id
            )
            order.margin_rule_id = rule.id if rule else False
            
            if rule and rule.line_ids:
                # Find applicable line for this margin
                line = False
                for rule_line in rule.line_ids:
                    if rule_line.min_margin <= order.margin_percentage <= rule_line.max_margin:
                        line = rule_line
                        break
                
                order.margin_rule_line_id = line.id if line else False
                order.margin_approval_user_ids = line.approver_ids if line else False
            else:
                order.margin_rule_line_id = False
                order.margin_approval_user_ids = False
    
    def _create_approval_notification_activity(self, action_type, rejection_reason=None):
        """Create activity to notify salesperson about approval/rejection
        
        Args:
            action_type: 'approved' or 'rejected'
            rejection_reason: Optional rejection reason to include in notification
        """
        self.ensure_one()
        
        if not self.user_id:
            return
        
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        if not activity_type:
            return
        
        if action_type == 'approved':
            summary = _('✅ Margin Approved: %s') % self.name
            note = f"""
                <p><strong style="color: green;">Margin ได้รับการอนุมัติแล้ว</strong></p>
                <p>Sales Order: <strong>{self.name}</strong></p>
                <p>ลูกค้า: {self.partner_id.name}</p>
                <p>Margin: <strong>{self.margin_percentage:.2f}%</strong></p>
                <p>ยอดรวม: {self.amount_total:,.2f} {self.currency_id.symbol}</p>
                <p>อนุมัติโดย: {self.env.user.name}</p>
                <p><strong>คุณสามารถดำเนินการ "Confirm To SO" ได้แล้ว</strong></p>
            """
        else:  # rejected
            summary = _('❌ Margin Rejected: %s') % self.name
            note = f"""
                <p><strong style="color: red;">Margin ถูกปฏิเสธ</strong></p>
                <p>Sales Order: <strong>{self.name}</strong></p>
                <p>ลูกค้า: {self.partner_id.name}</p>
                <p>Margin: <strong>{self.margin_percentage:.2f}%</strong></p>
                <p>ปฏิเสธโดย: {self.env.user.name}</p>
            """
            if rejection_reason:
                note += f"""
                <p><strong style="color: red;">เหตุผลการปฏิเสธ:</strong></p>
                <p style="background-color: #ffeeee; padding: 10px; border-left: 4px solid red;">
                    {rejection_reason}
                </p>
                """
            note += """
                <p><strong>กรุณาตรวจสอบและแก้ไข quotation แล้วขออนุมัติใหม่</strong></p>
            """
        
        # Delete old notification activities first
        old_activities = self.env['mail.activity'].search([
            ('res_model', '=', 'sale.order'),
            ('res_id', '=', self.id),
            ('user_id', '=', self.user_id.id),
            ('activity_type_id', '=', activity_type.id),
            ('summary', 'ilike', self.name),
        ])
        old_activities.unlink()
        
        # Create new activity
        self.env['mail.activity'].create({
            'activity_type_id': activity_type.id,
            'user_id': self.user_id.id,
            'res_id': self.id,
            'res_model_id': self.env['ir.model'].sudo().search([('model', '=', 'sale.order')], limit=1).id,
            'summary': summary,
            'note': note,
            'date_deadline': fields.Date.context_today(self),
        })
    
    def _can_approve_margin(self):
        """Check if current user can approve this order's margin
        
        Returns True if:
        - User has admin group (group_margin_approval_admin), OR
        - User has general approval group (group_margin_approval), OR  
        - User is in this order's margin_approval_user_ids
        """
        self.ensure_one()
        # Admin group can approve any order
        if self.env.user.has_group('buz_margin_approval.group_margin_approval_admin'):
            return True
        # General approval group can approve
        if self.env.user.has_group('buz_margin_approval.group_margin_approval'):
            return True
        # Or user must be in the specific approver list for this order
        return self.env.user in self.margin_approval_user_ids
    
    def action_confirm(self):
        """Override to enforce Confirm To SO flow for sales users"""
        for order in self:
            # Check if user is in sales margin approver user group
            is_sales_user = self.env.user.has_group('buz_margin_approval.group_sales_margin_approver_user')
            
            # Sales users are NOT allowed to use "Confirm Sale" button at all
            # They must use "Confirm To SO" and wait for Admin/Finance to confirm
            if is_sales_user:
                raise UserError(_(
                    "Sales users cannot confirm orders directly.\n"
                    "Please use 'Confirm To SO' button and wait for Admin/Finance to finalize the order."
                ))
            
            # Check margin approval
            if order.approval_state == 'pending':
                raise UserError(_(
                    "Cannot confirm! This order has a margin of %.2f%% which requires approval. "
                    "Please wait for approval from an authorized person."
                ) % order.margin_percentage)
            
            if order.approval_state == 'rejected':
                raise UserError(_(
                    "Cannot confirm! This order's margin has been rejected. "
                    "Please revise the order."
                ))
        
        result = super(SaleOrder, self).action_confirm()
        
        # Update confirm_flow_state to sale after confirmation
        for order in self:
            order.confirm_flow_state = 'sale'
        
        return result
    
    def action_request_margin_approval(self):
        """Request margin approval from approvers"""
        self.ensure_one()
        
        # Check if already approved or pending
        if self.approval_state == 'pending':
            raise UserError(_("This order is already pending approval."))
        
        if self.approval_state == 'approved':
            raise UserError(_("This order has already been approved."))
        
        # Check if user is in any margin rule
        if not self.margin_rule_id:
            raise UserError(_(
                "You are not assigned to any margin approval rule. "
                "This quotation does not require margin approval."
            ))
        
        # Check if order has lines
        if not self.order_line:
            raise UserError(_("Please add order lines before requesting margin approval."))
        
        # Check if margin is within approval range
        if not self.margin_rule_line_id:
            raise UserError(_(
                "Your margin (%.2f%%) does not require approval. "
                "The margin may be above the threshold or no approval rule is configured for this range."
            ) % self.margin_percentage)
        
        # Check if there are approvers
        if not self.margin_approval_user_ids:
            raise UserError(_(
                "No approvers are defined for the margin range (%.2f%%). "
                "Please contact your administrator to configure approvers."
            ) % self.margin_percentage)
        
        # All checks passed - proceed with approval request
        self.approval_state = 'pending'
        self.approved_user_ids = [(5, 0, 0)]  # Clear previous approvals
        
        # Create a record in mail thread for traceability
        body = _("Margin Approval Requested. Order margin: %.2f%%") % self.margin_percentage
        self.message_post(body=body)
        
        # Create mail activities for approvers
        self._create_margin_approval_activities()
        
        return True
    
    def action_approve_margin(self):
        """Approve margin by authorized user"""
        self.ensure_one()
        
        if not self._can_approve_margin():
            raise UserError(_("You are not authorized to approve this order's margin."))
        
        if self.approval_state != 'pending':
            raise UserError(_("This order is not pending approval."))
        
        # Add current user to approved users
        self.approved_user_ids = [(4, self.env.user.id)]
        
        # Check if approval is complete based on approval_type
        if self.approval_type == 'any':
            # Any one approver is enough
            self.approval_state = 'approved'
            self.margin_approval_date = fields.Datetime.now()
            self._mark_margin_approval_activities_done()
        elif self.approval_type == 'all':
            # Check if all approvers have approved
            if set(self.approved_user_ids.ids) >= set(self.margin_approval_user_ids.ids):
                self.approval_state = 'approved'
                self.margin_approval_date = fields.Datetime.now()
                self._mark_margin_approval_activities_done()
        
        body = _("Margin Approved by %s") % self.env.user.name
        if self.approval_state == 'approved':
            body += _(" - All required approvals obtained")
        self.message_post(body=body)
        
        # Create activity for salesperson notification
        if self.approval_state == 'approved':
            self._create_approval_notification_activity('approved')
        
        return True
    
    def action_reject_margin(self):
        """Reject margin - opens wizard for reason"""
        self.ensure_one()
        
        if not self._can_approve_margin():
            raise UserError(_("You are not authorized to reject this order's margin."))
        
        return {
            'name': _('Reject Margin'),
            'view_mode': 'form',
            'res_model': 'margin.rejection.wizard',
            'type': 'ir.actions.act_window',
            'target': 'new',
            'context': {'default_sale_order_id': self.id}
        }
    
    def action_cancel_margin_approval(self):
        """Cancel pending margin approval request by sales user.
        
        Only allowed when:
        - approval_state is 'pending' (not yet approved/rejected)
        - Order is still in draft/sent state
        
        Actions:
        - Reset approval_state to 'not_required'
        - Clear approved_user_ids
        - Cancel all pending approval activities (notifications to approvers)
        - Log in chatter
        """
        self.ensure_one()

        if self.approval_state != 'pending':
            raise UserError(_("You can only cancel a pending approval request."))

        if self.state not in ('draft', 'sent'):
            raise UserError(_("You can only cancel approval on a draft or sent quotation."))

        # Reset approval state
        self.approval_state = 'not_required'
        self.approved_user_ids = [(5, 0, 0)]

        # Cancel all pending approval activities for approvers
        self._cancel_margin_approval_activities()

        # Log in chatter
        body = _(
            "<strong>⚠️ Margin Approval Request Cancelled by %s</strong><br/>"
            "The approval request has been withdrawn.<br/>"
            "You may now edit the quotation and submit a new approval request."
        ) % self.env.user.name
        self.message_post(body=body)

        return True

    def _cancel_margin_approval_activities(self):
        """Cancel all pending margin approval activities for this order"""
        self.ensure_one()

        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        if not activity_type:
            return

        # Find all pending approval activities for this order (from any approver)
        activities = self.env['mail.activity'].search([
            ('res_model', '=', 'sale.order'),
            ('res_id', '=', self.id),
            ('activity_type_id', '=', activity_type.id),
        ])

        for activity in activities:
            activity.action_feedback(feedback=_('Approval request cancelled by sales user'))

    def action_confirm_to_so(self):
        """Confirm To SO - for Sales users (does NOT call action_confirm)"""
        self.ensure_one()
        
        # Check approval
        if self.approval_state not in ('approved', 'not_required'):
            raise UserError(_(
                "Cannot proceed! This order requires margin approval. "
                "Current approval status: %s"
            ) % dict(self._fields['approval_state'].selection).get(self.approval_state))
        
        # Check if all order lines have analytic account assigned
        lines_without_analytic = self.order_line.filtered(lambda line: not line.analytic_distribution)
        if lines_without_analytic:
            raise UserError(_(
                "Validation Error\n\n"
                "One or more lines require a 100% analytic distribution."
            ))
        
        # Update state
        self.confirm_flow_state = 'confirm_to_so'
        
        # Log in chatter
        body = _("Order moved to 'Confirm To SO' state by %s") % self.env.user.name
        self.message_post(body=body)
        
        return True
    
    def action_cancel_confirm_to_so(self):
        """Cancel Confirm To SO - Reset to draft and require re-approval"""
        self.ensure_one()
        
        # Check if order is in confirm_to_so state
        if self.confirm_flow_state != 'confirm_to_so':
            raise UserError(_("This order is not in 'Confirm To SO' state."))
        
        # Reset states
        self.confirm_flow_state = 'draft'
        self.approval_state = 'rejected'  # Force re-approval
        self.approved_user_ids = [(5, 0, 0)]  # Clear all approvals
        
        # Mark any pending activities as done
        self._mark_margin_approval_activities_done()
        
        # Log in chatter
        body = _(
            "<strong>Confirm To SO Cancelled by %s</strong><br/>"
            "Order has been reset to Quotation state.<br/>"
            "Sales user must re-submit for margin approval."
        ) % self.env.user.name
        self.message_post(body=body)
        
        # Create activity for the salesperson
        self._create_cancel_notification_activity()

        return True

    def action_rewrite_quotation(self):
        """Rewrite Quotation - กลับมาแก้ไขราคาหลังจาก customer ปฏิเสธ

        Flow:
        1. Sales ส่ง quotation ให้ลูกค้าแล้ว (approved state)
        2. ลูกค้าปฏิเสธ/ต่อรองราคา
        3. Sales กด Rewrite Quotation → กลับมาแก้ไขราคาได้
        4. แก้ไขเสร็จ → กด Request Margin Approval ใหม่

        Actions:
        - เพิ่ม rewrite_count +1
        - Reset approval_state → 'not_required' (ให้ request ใหม่ได้)
        - Reset confirm_flow_state → 'draft'
        - Clear approved_user_ids
        - Mark pending activities done
        - สร้าง activity แจ้งเตือน salesperson
        """
        self.ensure_one()

        # Only allowed when approval_state is 'approved'
        if self.approval_state != 'approved':
            raise UserError(_(
                "You can only rewrite a quotation that has been approved."
            ))

        # Only allowed in draft/sent state
        if self.state not in ('draft', 'sent'):
            raise UserError(_(
                "You can only rewrite a draft or sent quotation."
            ))

        # Increment rewrite count
        self.rewrite_count += 1
        new_version = self.rewrite_count

        # Reset approval state so sales can request again
        self.approval_state = 'not_required'
        self.margin_approval_date = False
        self.approved_user_ids = [(5, 0, 0)]  # Clear approvals
        self.confirm_flow_state = 'draft'  # Reset confirm flow

        # Mark old approval activities as done
        self._mark_margin_approval_activities_done()

        # Create activity for salesperson to remind to re-edit (log in activity only, no chatter)
        self._create_rewrite_notification_activity(new_version)

        return True

    def _create_rewrite_notification_activity(self, version):
        """Create activity to notify salesperson about rewrite action"""
        self.ensure_one()

        if not self.user_id:
            return

        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        if not activity_type:
            return

        summary = _('📝 Rewrite Quotation v%s: %s') % (version, self.name)
        note = f"""
            <p><strong style="color: orange;">Quotation Rewrite — Version {version}</strong></p>
            <p>Sales Order: <strong>{self.name}</strong></p>
            <p>ลูกค้า: {self.partner_id.name}</p>
            <p>Rewrite โดย: {self.env.user.name}</p>
            <p><strong>Action Required:</strong></p>
            <ul>
                <li>แก้ไขราคา/ส่วนลดตามที่ลูกค้าต้องการ</li>
                <li>ตรวจสอบ Margin ใหม่</li>
                <li>กด <strong>Request Margin Approval</strong> เพื่อขออนุมัติใหม่</li>
            </ul>
        """

        # Delete old activities first
        old_activities = self.env['mail.activity'].search([
            ('res_model', '=', 'sale.order'),
            ('res_id', '=', self.id),
            ('user_id', '=', self.user_id.id),
            ('summary', 'ilike', self.name),
        ])
        old_activities.unlink()

        # Create new activity
        self.env['mail.activity'].create({
            'activity_type_id': activity_type.id,
            'user_id': self.user_id.id,
            'res_id': self.id,
            'res_model_id': self.env['ir.model'].sudo().search([('model', '=', 'sale.order')], limit=1).id,
            'summary': summary,
            'note': note,
            'date_deadline': fields.Date.context_today(self),
        })

    def _create_cancel_notification_activity(self):
        """Create activity to notify salesperson about cancellation"""
        self.ensure_one()
        
        if not self.user_id:
            return
        
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        if not activity_type:
            return
        
        summary = _('⚠️ Confirm To SO Cancelled: %s') % self.name
        note = f"""
            <p><strong style="color: orange;">Confirm To SO has been cancelled</strong></p>
            <p>Sales Order: <strong>{self.name}</strong></p>
            <p>Customer: {self.partner_id.name}</p>
            <p>Cancelled by: {self.env.user.name}</p>
            <p><strong>Action Required:</strong></p>
            <ul>
                <li>Review the quotation</li>
                <li>Make necessary adjustments</li>
                <li>Request margin approval again</li>
            </ul>
        """
        
        # Delete old activities first
        old_activities = self.env['mail.activity'].search([
            ('res_model', '=', 'sale.order'),
            ('res_id', '=', self.id),
            ('user_id', '=', self.user_id.id),
            ('summary', 'ilike', self.name),
        ])
        old_activities.unlink()
        
        # Create new activity
        self.env['mail.activity'].create({
            'activity_type_id': activity_type.id,
            'user_id': self.user_id.id,
            'res_id': self.id,
            'res_model_id': self.env['ir.model'].sudo().search([('model', '=', 'sale.order')], limit=1).id,
            'summary': summary,
            'note': note,
            'date_deadline': fields.Date.context_today(self),
        })
    
    def write(self, vals):
        """Reset approval when price/discount changes"""
        reset_approval = False
        
        # Check if order lines are being modified
        if 'order_line' in vals:
            for command in vals['order_line']:
                # command[0]: 0=create, 1=update, 2=delete, 3=unlink, 4=link, 5=clear, 6=replace
                if command[0] in (0, 1, 2):
                    line_vals = command[2] if len(command) > 2 else {}
                    if command[0] == 2 or any(field in line_vals for field in ['price_unit', 'discount', 'product_uom_qty', 'product_id']):
                        reset_approval = True
                        break
        
        # Reset approval if order was approved and prices changed
        if reset_approval:
            for order in self:
                if order.approval_state == 'approved':
                    vals['approval_state'] = 'not_required'  # Reset to allow re-request
                    vals['margin_approval_date'] = False
                    vals['approved_user_ids'] = [(5, 0, 0)]  # Clear approvals
                    vals['confirm_flow_state'] = 'draft'  # Reset confirm flow too
                    # Mark old activities as done
                    order._mark_margin_approval_activities_done()
                    # Post message about reset
                    order.message_post(body=_(
                        "<strong>⚠️ Order Modified - Approval Reset</strong><br/>"
                        "Price or quantity has been changed.<br/>"
                        "Please request margin approval again."
                    ))
        
        return super(SaleOrder, self).write(vals)
    
    def _create_margin_approval_activities(self):
        """Create mail activity for each margin approver"""
        self.ensure_one()
        mail_activity = self.env['mail.activity']
        
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        if not activity_type:
            return
        
        for approver in self.margin_approval_user_ids:
            # Delete old pending activities first
            old_activities = mail_activity.search([
                ('res_model', '=', 'sale.order'),
                ('res_id', '=', self.id),
                ('user_id', '=', approver.id),
                ('activity_type_id', '=', activity_type.id),
            ])
            old_activities.unlink()
            
            # Create new activity
            mail_activity.create({
                'activity_type_id': activity_type.id,
                'user_id': approver.id,
                'res_id': self.id,
                'res_model_id': self.env['ir.model'].sudo().search([('model', '=', 'sale.order')], limit=1).id,
                'summary': _('อนุมัติ Margin ของใบสั่งขาย: %s') % self.name,
                'note': f"""
                    <p>Sales Order: <strong>{self.name}</strong></p>
                    <p>ลูกค้า: {self.partner_id.name}</p>
                    <p>Margin: <strong>{self.margin_percentage:.2f}%</strong></p>
                    <p>ยอดรวม: {self.amount_total:,.2f} {self.currency_id.symbol}</p>
                    <p>พนักงานขาย: {self.user_id.name}</p>
                    <p>กรุณาตรวจสอบและอนุมัติหรือปฏิเสธคำขอนี้</p>
                """,
                'date_deadline': fields.Date.context_today(self),
            })
    
    def _mark_margin_approval_activities_done(self):
        """Mark margin approval activities as done"""
        self.ensure_one()
        mail_activity = self.env['mail.activity']
        
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        if not activity_type:
            return
        
        activities = mail_activity.search([
            ('res_model', '=', 'sale.order'),
            ('res_id', '=', self.id),
            ('activity_type_id', '=', activity_type.id),
            ('user_id', 'in', self.margin_approval_user_ids.ids),
        ])
        
        for activity in activities:
            activity.action_feedback(feedback=_('Margin Approved'))
    
    def _mark_margin_approval_activities_rejected(self, rejection_reason=''):
        """Mark margin approval activities as rejected"""
        self.ensure_one()
        mail_activity = self.env['mail.activity']
        
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        if not activity_type:
            return
        
        activities = mail_activity.search([
            ('res_model', '=', 'sale.order'),
            ('res_id', '=', self.id),
            ('activity_type_id', '=', activity_type.id),
            ('user_id', 'in', self.margin_approval_user_ids.ids),
        ])
        
        feedback_msg = _('Margin Rejected')
        if rejection_reason:
            feedback_msg = _('Margin Rejected - เหตุผล: %s') % rejection_reason
        
        for activity in activities:
            activity.action_feedback(feedback=feedback_msg)
