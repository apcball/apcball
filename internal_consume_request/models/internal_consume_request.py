# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class InternalConsumeRequest(models.Model):
    _name = 'internal.consume.request'
    _description = 'Internal Consumable Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'request_date desc, id desc'

    name = fields.Char(
        string='Reference',
        required=True,
        readonly=True,
        default='New',
        copy=False,
        tracking=True
    )
    
    request_date = fields.Date(
        string='Request Date',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
        states={'to_approve': [('readonly', True)], 'approved': [('readonly', True)], 'done': [('readonly', True)], 'rejected': [('readonly', True)]}
    )
    
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        default=lambda self: self.env.user.employee_id,
        tracking=True,
        states={'to_approve': [('readonly', True)], 'approved': [('readonly', True)], 'done': [('readonly', True)], 'rejected': [('readonly', True)]}
    )
    
    department_id = fields.Many2one(
        'hr.department',
        string='Department',
        related='employee_id.department_id',
        store=True,
        readonly=True
    )
    
    manager_id = fields.Many2one(
        'hr.employee',
        string='Head of Department',
        related='employee_id.coach_id',
        store=True,
        readonly=True
    )
    
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Warehouse',
        required=True,
        default=lambda self: self._default_warehouse_id(),
        tracking=True,
        states={'to_approve': [('readonly', True)], 'approved': [('readonly', True)], 'done': [('readonly', True)], 'rejected': [('readonly', True)]}
    )
    
    picking_type_id = fields.Many2one(
        'stock.picking.type',
        string='Picking Type',
        required=True,
        domain="[('code', 'in', ['outgoing', 'internal']), ('warehouse_id', '=', warehouse_id)]",
        compute='_compute_picking_type_id',
        store=True,
        readonly=False,
        states={'to_approve': [('readonly', True)], 'approved': [('readonly', True)], 'done': [('readonly', True)], 'rejected': [('readonly', True)]}
    )
    
    location_id = fields.Many2one(
        'stock.location',
        string='Source Location',
        required=True,
        domain="[('usage', '=', 'internal')]",
        compute='_compute_location_id',
        store=True,
        readonly=False,
        states={'to_approve': [('readonly', True)], 'approved': [('readonly', True)], 'done': [('readonly', True)], 'rejected': [('readonly', True)]}
    )
    
    location_dest_id = fields.Many2one(
        'stock.location',
        string='Destination Location',
        required=True,
        domain="[('usage', 'in', ['customer', 'inventory'])]",
        default=lambda self: self._default_location_dest_id(),
        states={'to_approve': [('readonly', True)], 'approved': [('readonly', True)], 'done': [('readonly', True)], 'rejected': [('readonly', True)]}
    )
    
    partner_id = fields.Many2one(
        'res.partner',
        string='Partner',
        compute='_compute_partner_id',
        store=True,
        readonly=True
    )
    
    responsible_id = fields.Many2one(
        'res.users',
        string='Responsible',
        required=True,
        tracking=True,
        help='เจ้าหน้าที่คลังสินค้าที่รับผิดชอบจ่ายของ',
        states={'done': [('readonly', True)], 'rejected': [('readonly', True)]}
    )
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('to_approve', 'To Approve'),
        ('approved', 'Approved'),
        ('done', 'Done'),
        ('rejected', 'Rejected')
    ], string='Status', default='draft', required=True, tracking=True, copy=False)
    
    line_ids = fields.One2many(
        'internal.consume.request.line',
        'request_id',
        string='Request Lines',
        states={'to_approve': [('readonly', True)], 'approved': [('readonly', True)], 'done': [('readonly', True)], 'rejected': [('readonly', True)]}
    )
    
    picking_id = fields.Many2one(
        'stock.picking',
        string='Delivery Transfer',
        readonly=True,
        copy=False
    )
    
    picking_count = fields.Integer(
        string='Picking Count',
        compute='_compute_picking_count'
    )
    
    rejection_reason = fields.Text(
        string='Rejection Reason',
        tracking=True
    )
    
    notes = fields.Text(
        string='Notes',
        states={'to_approve': [('readonly', True)], 'approved': [('readonly', True)], 'done': [('readonly', True)], 'rejected': [('readonly', True)]}
    )
    
    reason_for_requisition = fields.Text(
        string='Reason For Requisition',
        tracking=True,
        help='เหตุผลในการขอเบิกวัสดุ/อุปกรณ์',
        states={'to_approve': [('readonly', True)], 'approved': [('readonly', True)], 'done': [('readonly', True)], 'rejected': [('readonly', True)]}
    )
    
    # New fields for auto-reject functionality
    has_insufficient_stock = fields.Boolean(
        string='Has Insufficient Stock',
        compute='_compute_has_insufficient_stock',
        store=False,
        help='True if any line has insufficient stock'
    )
    
    allow_submit = fields.Boolean(
        string='Allow Submit',
        compute='_compute_allow_submit',
        store=False,
        help='True if request can be submitted (sufficient stock)'
    )
    
    reason = fields.Text(
        string='Auto Reject Reason',
        help='Automatic rejection reason when stock is insufficient'
    )

    @api.model
    def _default_warehouse_id(self):
        """Default warehouse - get first available warehouse"""
        warehouse = self.env['stock.warehouse'].search([], limit=1)
        return warehouse

    @api.model
    def _default_location_dest_id(self):
        """Default destination location to Customers (virtual location)"""
        # Use customer location for consuming stock
        location = self.env.ref('stock.stock_location_customers', raise_if_not_found=False)
        if not location:
            # Fallback to any customer location
            location = self.env['stock.location'].search([
                ('usage', '=', 'customer')
            ], limit=1)
        return location

    @api.depends('warehouse_id')
    def _compute_picking_type_id(self):
        """Compute picking type based on selected warehouse - default to delivery"""
        for record in self:
            if record.warehouse_id:
                # Default to delivery (outgoing) type, but allow user to change to internal
                record.picking_type_id = record.warehouse_id.out_type_id
            else:
                record.picking_type_id = False

    @api.depends('picking_type_id')
    def _compute_location_id(self):
        """Compute source location based on picking type"""
        for record in self:
            if record.picking_type_id:
                record.location_id = record.picking_type_id.default_location_src_id
            elif record.warehouse_id:
                record.location_id = record.warehouse_id.lot_stock_id
            else:
                record.location_id = False
    
    @api.onchange('picking_type_id')
    def _onchange_picking_type_id(self):
        """Update locations when picking type changes"""
        if self.picking_type_id:
            self.location_id = self.picking_type_id.default_location_src_id
            self.location_dest_id = self.picking_type_id.default_location_dest_id

    @api.depends('employee_id', 'employee_id.user_id', 'employee_id.user_id.partner_id')
    def _compute_partner_id(self):
        for record in self:
            if record.employee_id and record.employee_id.user_id:
                record.partner_id = record.employee_id.user_id.partner_id
            else:
                record.partner_id = False

    @api.depends('picking_id')
    def _compute_picking_count(self):
        for record in self:
            record.picking_count = 1 if record.picking_id else 0
    
    @api.depends('line_ids', 'line_ids.qty_requested', 'line_ids.available_qty')
    def _compute_has_insufficient_stock(self):
        """Check if any line has insufficient stock"""
        for record in self:
            has_insufficient = False
            for line in record.line_ids:
                if line.qty_requested > line.available_qty:
                    has_insufficient = True
                    break
            record.has_insufficient_stock = has_insufficient
    
    @api.depends('has_insufficient_stock', 'line_ids')
    def _compute_allow_submit(self):
        """Allow submit only if stock is sufficient and lines exist"""
        for record in self:
            record.allow_submit = bool(record.line_ids) and not record.has_insufficient_stock

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'internal.consume.request') or 'New'
        return super().create(vals_list)
    
    def copy(self, default=None):
        """Override copy method to ensure all lines are properly duplicated"""
        if default is None:
            default = {}
        
        # Ensure line_ids are copied with all their data
        if 'line_ids' not in default:
            new_line_ids = []
            for line in self.line_ids:
                # Prepare line values for copying
                line_vals = {
                    'product_id': line.product_id.id,
                    'description': line.description,
                    'product_uom_id': line.product_uom_id.id,
                    'qty_requested': line.qty_requested,
                    'analytic_distribution': line.analytic_distribution or {},
                    'sequence': line.sequence,
                }
                new_line_ids.append((0, 0, line_vals))
            default['line_ids'] = new_line_ids
        
        return super().copy(default)

    @api.constrains('line_ids')
    def _check_lines(self):
        for record in self:
            if not record.line_ids:
                raise ValidationError(_('Please add at least one product line.'))

    def action_submit(self):
        """Submit request for approval - with auto-reject for insufficient stock"""
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_('Please add at least one product line before submitting.'))
        
        # Check if all lines have analytic distribution
        for line in self.line_ids:
            if not line.analytic_distribution or not any(line.analytic_distribution.values()):
                raise UserError(
                    _('Please enter Analytic Distribution for all items before submitting for approval.')
                )
        
        # Check stock availability before submit
        insufficient_lines = []
        for line in self.line_ids:
            if line.qty_requested > line.available_qty:
                insufficient_lines.append({
                    'product': line.product_id.display_name,
                    'requested': line.qty_requested,
                    'available': line.available_qty,
                })
        
        # Auto reject if insufficient stock
        if insufficient_lines:
            reason_lines = []
            reason_lines.append(_('Stock ไม่เพียงพอสำหรับสินค้าต่อไปนี้:'))
            for info in insufficient_lines:
                reason_lines.append(
                    _('- %s: ขอเบิก %.2f แต่มีเพียง %.2f') % (
                        info['product'], info['requested'], info['available']
                    )
                )
            reason = '\n'.join(reason_lines)
            
            # Call auto reject
            self._action_auto_reject(reason)
            
            raise UserError(
                _('Request has been automatically rejected due to insufficient stock.\n\n%s') % reason
            )
        
        if not self.manager_id:
            raise UserError(_('No manager found for employee %s. Please set a manager first.') % self.employee_id.name)
        
        if not self.manager_id.user_id:
            raise UserError(_('Manager %s does not have a user account.') % self.manager_id.name)
        
        self.state = 'to_approve'
        
        # Create mail activity for manager
        self.activity_schedule(
            'mail.mail_activity_data_todo',
            user_id=self.manager_id.user_id.id,
            summary=_('อนุมัติขอเบิกอุปกรณ์สิ้นเปลือง'),
            note=_('Please approve the internal consumable request %s from %s') % (
                self.name, self.employee_id.name
            )
        )
        
        self.message_post(
            body=_('Request submitted for approval to %s') % self.manager_id.name,
            message_type='notification',
            subtype_xmlid='mail.mt_note'
        )

    def action_approve(self):
        """Approve request and create picking - with stock validation"""
        self.ensure_one()
        
        # Check stock availability before approval
        if self.has_insufficient_stock:
            raise UserError(
                _('Cannot approve: Insufficient stock for one or more items. '
                  'Please check the available quantities.')
            )
        
        # Mark activity as done
        activity = self.env['mail.activity'].search([
            ('res_id', '=', self.id),
            ('res_model', '=', self._name),
            ('user_id', '=', self.env.user.id)
        ], limit=1)
        if activity:
            activity.action_feedback(feedback='Approved')
        
        self.state = 'approved'
        
        self.message_post(
            body=_('Request approved by %s') % self.env.user.name,
            message_type='notification',
            subtype_xmlid='mail.mt_note'
        )
        
        # Send activity to Responsible user if assigned
        if self.responsible_id:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=self.responsible_id.id,
                summary=_('จ่ายของตามเอกสารขอเบิก: %s') % self.name,
                note=_('เอกสารขอเบิกได้รับการอนุมัติแล้ว กรุณาดำเนินการจ่ายของตามรายการที่ขอเบิก<br/>'
                       'พนักงาน: %s<br/>'
                       'แผนก: %s') % (
                    self.employee_id.name,
                    self.department_id.name if self.department_id else '-'
                )
            )
        
        # Auto create picking
        self.action_create_picking()

    def action_reject(self):
        """Reject request"""
        self.ensure_one()
        
        # Open wizard for rejection reason
        return {
            'name': _('Reject Request'),
            'type': 'ir.actions.act_window',
            'res_model': 'internal.consume.request.reject',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_request_id': self.id}
        }

    def _action_reject_with_reason(self, reason):
        """Internal method to reject with reason (manual rejection)"""
        self.ensure_one()
        
        # Mark activity as done
        activity = self.env['mail.activity'].search([
            ('res_id', '=', self.id),
            ('res_model', '=', self._name),
            ('user_id', '=', self.env.user.id)
        ], limit=1)
        if activity:
            activity.action_feedback(feedback='Rejected: %s' % reason)
        
        self.write({
            'state': 'rejected',
            'rejection_reason': reason
        })
        
        self.message_post(
            body=_('Request rejected by %s<br/>Reason: %s') % (self.env.user.name, reason),
            message_type='notification',
            subtype_xmlid='mail.mt_note'
        )
    
    def _action_auto_reject(self, reason):
        """Auto reject request due to insufficient stock"""
        self.ensure_one()
        
        # Mark any pending activity as done
        activities = self.env['mail.activity'].search([
            ('res_id', '=', self.id),
            ('res_model', '=', self._name),
        ])
        for activity in activities:
            activity.action_feedback(feedback='Auto-rejected: Insufficient stock')
        
        # Update state and reason
        self.write({
            'state': 'rejected',
            'rejection_reason': reason,
            'reason': reason,
        })
        
        # Post message
        self.message_post(
            body=_('Request automatically rejected due to insufficient stock<br/>%s') % reason,
            message_type='notification',
            subtype_xmlid='mail.mt_note'
        )
        
        # Create activity for employee to notify
        if self.employee_id and self.employee_id.user_id:
            self.activity_schedule(
                'mail.mail_activity_data_warning',
                user_id=self.employee_id.user_id.id,
                summary=_('คำขอเบิกถูกปฏิเสธอัตโนมัติ - Stock ไม่เพียงพอ'),
                note=_('Your request %s has been automatically rejected due to insufficient stock:\n\n%s') % (
                    self.name, reason
                )
            )

    def action_create_picking(self):
        """Create stock picking from request (Delivery to consume stock) - with final stock validation"""
        self.ensure_one()
        
        if self.picking_id:
            raise UserError(_('Picking already created for this request.'))
        
        if not self.line_ids:
            raise UserError(_('No lines to create picking.'))
        
        # Final stock validation before creating picking
        insufficient_lines = []
        for line in self.line_ids:
            if line.qty_requested > line.available_qty:
                insufficient_lines.append({
                    'product': line.product_id.display_name,
                    'requested': line.qty_requested,
                    'available': line.available_qty,
                })
        
        # Auto reject if stock changed and is now insufficient
        if insufficient_lines:
            reason_lines = []
            reason_lines.append(_('Stock ไม่เพียงพอ (ตรวจสอบก่อนสร้าง Picking):'))
            for info in insufficient_lines:
                reason_lines.append(
                    _('- %s: ขอเบิก %.2f แต่มีเพียง %.2f') % (
                        info['product'], info['requested'], info['available']
                    )
                )
            reason = '\n'.join(reason_lines)
            
            # Auto reject
            self._action_auto_reject(reason)
            
            raise UserError(
                _('Request has been automatically rejected.\n'
                  'Stock levels changed before creating picking.\n\n%s') % reason
            )
        
        # Prepare picking values for delivery/consumption
        picking_vals = {
            'picking_type_id': self.picking_type_id.id,
            'location_id': self.location_id.id,
            'location_dest_id': self.location_dest_id.id,
            'origin': self.name,
            'scheduled_date': fields.Datetime.now(),
            'partner_id': self.partner_id.id if self.partner_id else False,
            'move_ids_without_package': []
        }
        
        # Prepare move lines
        for line in self.line_ids:
            if line.qty_requested <= 0:
                continue
            
            move_vals = {
                'name': line.product_id.display_name or '/',
                'product_id': line.product_id.id,
                'product_uom_qty': line.qty_requested,
                'product_uom': line.product_uom_id.id,
                'location_id': self.location_id.id,
                'location_dest_id': self.location_dest_id.id,
                'description_picking': line.description or line.product_id.display_name,
            }
            picking_vals['move_ids_without_package'].append((0, 0, move_vals))
        
        # Create picking
        picking = self.env['stock.picking'].create(picking_vals)
        self.picking_id = picking.id
        
        self.message_post(
            body=_('Delivery order %s created from warehouse %s') % (picking.name, self.warehouse_id.name),
            message_type='notification',
            subtype_xmlid='mail.mt_note'
        )
        
        return {
            'name': _('Delivery Order'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'res_id': picking.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_picking(self):
        """View related picking"""
        self.ensure_one()
        if not self.picking_id:
            raise UserError(_('No picking found for this request.'))
        
        return {
            'name': _('Delivery Order'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'res_id': self.picking_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_done(self):
        """Mark request as done"""
        self.ensure_one()
        
        if not self.picking_id:
            raise UserError(_('Please create a delivery order first.'))
        
        if self.picking_id.state != 'done':
            raise UserError(_('Please validate the delivery order first.'))
        
        self.state = 'done'
        
        self.message_post(
            body=_('Request completed'),
            message_type='notification',
            subtype_xmlid='mail.mt_note'
        )

    def action_set_to_draft(self):
        """Reset to draft"""
        self.ensure_one()
        self.state = 'draft'

    def action_duplicate_request(self):
        """Duplicate the current request with all its lines"""
        self.ensure_one()
        
        # Create a copy of the request
        default_vals = {
            'name': 'New',  # Will be replaced by sequence in create method
            'request_date': fields.Date.context_today(self),
            'state': 'draft',
            'picking_id': False,  # Clear the picking reference
            'rejection_reason': False,  # Clear rejection reason
            'reason': False,  # Clear auto reject reason
        }
        
        # Copy the request
        new_request = self.copy(default_vals)
        
        # Return action to open the duplicated request
        return {
            'type': 'ir.actions.act_window',
            'name': _('Duplicated Request'),
            'res_model': 'internal.consume.request',
            'res_id': new_request.id,
            'view_mode': 'form',
            'target': 'current',
            'context': {'form_view_initial_mode': 'edit'},
        }

    def unlink(self):
        """Prevent deletion of non-draft records"""
        for record in self:
            if record.state not in ('draft', 'rejected'):
                raise UserError(_('You can only delete draft or rejected requests.'))
        return super().unlink()
