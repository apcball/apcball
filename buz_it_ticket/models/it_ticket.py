# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta
import json


class ItTicket(models.Model):
    _name = 'it.ticket'
    _description = 'IT Ticket'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'
    _rec_name = 'name'

    @api.model
    def _default_employee_id(self):
        """Get current employee"""
        employee = self.env['hr.employee'].search([('user_id', '=', self.env.uid)], limit=1)
        return employee if employee else False

    @api.model
    def _default_requester_email(self):
        """Get default email from employee"""
        employee = self._default_employee_id()
        if employee and employee.work_email:
            return employee.work_email
        elif employee and employee.user_id and employee.user_id.email:
            return employee.user_id.email
        return ''

    # Basic fields
    name = fields.Char('Ticket Number', copy=False, readonly=True)
    category = fields.Selection([
        ('issue', 'IT Request'),
        ('access', 'Access Request'),
        ('purchase', 'Purchase Request'),
    ], string='Category', required=True, default='issue')
    
    # State fields - different for each category
    state = fields.Selection([
        # Common states
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('cancelled', 'Cancelled'),
        
        # Issue/Repair states
        ('in_progress', 'In Progress'),
        ('pending_info', 'Pending Info'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
        
        # Access states
        ('waiting_manager', 'Waiting Manager'),
        ('approved', 'Approved'),
        ('implementing', 'Implementing'),
        ('rejected', 'Rejected'),
        
        # Purchase states
        ('waiting_it', 'Waiting IT'),
        ('po_created', 'PO Created'),
        ('received', 'Received'),
    ], string='State', default='draft', tracking=True)
    
    # Employee and responsibility
    employee_id = fields.Many2one('hr.employee', 'Requester', required=True, default=_default_employee_id)
    manager_id = fields.Many2one('hr.employee', 'Manager', compute='_compute_manager_id', store=True)
    it_responsible_id = fields.Many2one('res.users', 'IT Responsible')
    
    # Priority and classification
    sla_level = fields.Selection([
        ('standard', 'Standard (มาตรฐาน)'),
        ('important', 'Important (สำคัญ)'),
        ('urgent', 'Urgent (เร่งด่วน)'),
        ('critical', 'Critical (วิกฤต)'),
    ], string='Priority', default='important', tracking=True)
    
    # Organization
    company_id = fields.Many2one('res.company', 'Company', default=lambda self: self.env.company, required=True)
    department_id = fields.Many2one('hr.department', 'Department')
    user_id = fields.Many2one('res.users', 'Created By', default=lambda self: self.env.user)
    
    # Description
    description = fields.Html('Description')
    attachment_ids = fields.One2many('ir.attachment', 'res_id', 'Attachments',
                                    domain=[('res_model', '=', 'it.ticket')])
    
    # SLA fields
    sla_policy_id = fields.Many2one('it.sla.policy', 'SLA Policy')
    deadline_sla = fields.Datetime('SLA Deadline')
    responded_at = fields.Datetime('Responded At', readonly=True)
    resolved_at = fields.Datetime('Resolved At', readonly=True)
    ttr_respond = fields.Float('Time to Respond (hours)', readonly=True)
    ttr_resolve = fields.Float('Time to Resolve (hours)', readonly=True)
    sla_breached = fields.Boolean('SLA Breached', readonly=True)
    
    # Access specific fields
    access_template_id = fields.Many2one('it.access.template', 'Access Template')
    access_line_ids = fields.One2many('it.ticket.line', 'ticket_id', 
                                      domain=[('access_type', '!=', False)])
    
    # Purchase specific fields
    purchase_line_ids = fields.One2many('it.ticket.line', 'ticket_id',
                                        domain=[('product_id', '!=', False)])
    purchase_id = fields.Many2one('purchase.order', 'Purchase Order')
    
    # Issue specific fields
    requester_email = fields.Char('Email', required=True, default=lambda self: self._default_requester_email())
    line_id = fields.Char('ID LINE', required=True)
    symptoms = fields.Text('Symptoms/Issues (อาการเสีย)', required=True)
    computer_name = fields.Char('Computer Name', required=True)
    
    # ISO fields
    iso_doc_code = fields.Char('ISO Document Code')
    revision = fields.Char('Revision')
    printed_count = fields.Integer('Printed Count', default=0)
    printed_by = fields.Many2one('res.users', 'Printed By')
    printed_at = fields.Datetime('Printed At')
    
    @api.depends('employee_id')
    def _compute_manager_id(self):
        """Compute manager from employee"""
        for ticket in self:
            if ticket.employee_id and ticket.employee_id.parent_id:
                ticket.manager_id = ticket.employee_id.parent_id
            else:
                ticket.manager_id = False

    @api.constrains('category', 'requester_email', 'line_id', 'symptoms', 'computer_name')
    def _check_issue_required_fields(self):
        """Check that required fields are filled for Issue tickets"""
        for ticket in self:
            if ticket.category == 'issue':
                if not ticket.requester_email:
                    raise ValidationError(_('Email is required for Issue tickets'))
                if not ticket.line_id:
                    raise ValidationError(_('ID LINE is required for Issue tickets'))
                if not ticket.symptoms:
                    raise ValidationError(_('Symptoms/Issues is required for Issue tickets'))
                if not ticket.computer_name:
                    raise ValidationError(_('Computer Name is required for Issue tickets'))

    @api.onchange('sla_level', 'category')
    def _onchange_sla_level(self):
        """Automatically set SLA Policy based on SLA Level and Category"""
        if self.sla_level and self.category:
            sla_policy = self.env['it.sla.policy'].get_sla_policy(
                self.category, self.sla_level
            )
            if sla_policy:
                self.sla_policy_id = sla_policy

    @api.model
    def create(self, vals):
        """Override create to generate sequence number"""
        if vals.get('name', '/') == '/':
            vals['name'] = self._get_sequence_number(vals.get('category', 'issue'))
        return super(ItTicket, self).create(vals)

    def _get_sequence_number(self, category):
        """Get sequence number based on category"""
        if category == 'issue':
            return self.env['ir.sequence'].next_by_code('it.ticket.issue') or '/'
        elif category == 'access':
            return self.env['ir.sequence'].next_by_code('it.ticket.access') or '/'
        elif category == 'purchase':
            return self.env['ir.sequence'].next_by_code('it.ticket.purchase') or '/'
        return '/'

    # ===== ISSUE WORKFLOW =====
    
    def action_issue_submit(self):
        """Submit issue ticket"""
        self.ensure_one()
        if self.category != 'issue':
            raise UserError(_('This action is only for Issue tickets'))
        if self.state != 'draft':
            raise UserError(_('Only draft tickets can be submitted'))
        
        self.state = 'submitted'
        self._set_sla_policy()
        
        # Create activity for IT team
        if self.it_responsible_id:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=_('New Issue Ticket: %s') % self.name,
                note=_('A new issue ticket has been submitted. SLA Level: %s\n\n%s') % (self.sla_level, self.description or ''),
                user_id=self.it_responsible_id.id
            )
        
        self.message_post(body=_('Issue ticket submitted'))
        return True

    def action_issue_start_work(self):
        """Start working on issue"""
        self.ensure_one()
        if self.category != 'issue':
            raise UserError(_('This action is only for Issue tickets'))
        if self.state != 'submitted':
            raise UserError(_('Only submitted tickets can be started'))
        
        self.state = 'in_progress'
        self.message_post(body=_('Work started on issue ticket'))
        return True

    def action_issue_need_info(self):
        """Request more information from requester"""
        self.ensure_one()
        if self.category != 'issue':
            raise UserError(_('This action is only for Issue tickets'))
        if self.state not in ['in_progress', 'pending_info']:
            raise UserError(_('Only tickets in progress can request more info'))
        
        self.state = 'pending_info'
        if self.employee_id and self.employee_id.user_id:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=_('Information Required: %s') % self.name,
                note=_('Additional information is required for this ticket.'),
                user_id=self.employee_id.user_id.id
            )
        
        self.message_post(body=_('Requested additional information'))
        return True

    def action_issue_resolve(self):
        """Mark issue as resolved"""
        self.ensure_one()
        if self.category != 'issue':
            raise UserError(_('This action is only for Issue tickets'))
        if self.state not in ['in_progress', 'pending_info']:
            raise UserError(_('Only tickets in progress can be resolved'))
        
        self._record_resolve_time()
        self.state = 'resolved'
        self.message_post(body=_('Ticket resolved'))
        return True

    def action_issue_close(self):
        """Close issue ticket"""
        self.ensure_one()
        if self.category != 'issue':
            raise UserError(_('This action is only for Issue tickets'))
        if self.state not in ['resolved']:
            raise UserError(_('Only resolved tickets can be closed'))
        
        self.state = 'closed'
        self.message_post(body=_('Issue ticket closed'))
        return True

    def action_issue_cancel(self):
        """Cancel issue"""
        self.ensure_one()
        if self.category != 'issue':
            raise UserError(_('This action is only for Issue tickets'))
        
        self.state = 'cancelled'
        self.message_post(body=_('Issue ticket cancelled'))
        return True

    # ===== ACCESS WORKFLOW =====
    
    def action_access_submit(self):
        """Submit access request"""
        self.ensure_one()
        if self.category != 'access':
            raise UserError(_('This action is only for Access tickets'))
        if self.state != 'draft':
            raise UserError(_('Only draft tickets can be submitted'))
        
        if not self.access_line_ids:
            raise ValidationError(_('Please add at least one access request'))
        
        self.state = 'waiting_manager'
        self._set_sla_policy()
        
        # Send to manager for approval
        if self.manager_id and self.manager_id.user_id:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=_('Access Request Approval: %s') % self.name,
                note=_('An access request requires your approval.\n\n%s') % (self.description or ''),
                user_id=self.manager_id.user_id.id
            )
        
        self.message_post(body=_('Access request submitted and waiting for manager approval'))
        return True

    def action_access_manager_approve(self):
        """Manager approves access request"""
        self.ensure_one()
        if self.category != 'access':
            raise UserError(_('This action is only for Access tickets'))
        if self.state != 'waiting_manager':
            raise UserError(_('Only tickets waiting for manager approval can be approved'))
        
        self.state = 'approved'
        
        # Send to IT team
        if self.it_responsible_id:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=_('Access Request Approved: %s') % self.name,
                note=_('Access request has been approved. Please implement the requested access.'),
                user_id=self.it_responsible_id.id
            )
        
        self.message_post(body=_('Access request approved by manager'))
        return True

    def action_access_manager_reject(self):
        """Manager rejects access request"""
        self.ensure_one()
        if self.category != 'access':
            raise UserError(_('This action is only for Access tickets'))
        if self.state != 'waiting_manager':
            raise UserError(_('Only tickets waiting for manager approval can be rejected'))
        
        self.state = 'rejected'
        self.message_post(body=_('Access request rejected by manager'))
        return True

    def action_access_start_implement(self):
        """IT starts implementing access"""
        self.ensure_one()
        if self.category != 'access':
            raise UserError(_('This action is only for Access tickets'))
        if self.state != 'approved':
            raise UserError(_('Only approved tickets can be implemented'))
        
        self.state = 'implementing'
        self._record_response_time()
        self.message_post(body=_('Started implementing access'))
        return True

    def action_access_mark_done(self):
        """Mark access implementation as done"""
        self.ensure_one()
        if self.category != 'access':
            raise UserError(_('This action is only for Access tickets'))
        if self.state != 'implementing':
            raise UserError(_('Only implementing tickets can be marked as done'))
        
        self._record_resolve_time()
        self.state = 'closed'
        
        # Notify requester
        if self.employee_id and self.employee_id.user_id:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=_('Access Implemented: %s') % self.name,
                note=_('Your access request has been implemented.'),
                user_id=self.employee_id.user_id.id
            )
        
        self.message_post(body=_('Access implemented and ticket closed'))
        return True

    def action_access_cancel(self):
        """Cancel access request"""
        self.ensure_one()
        if self.category != 'access':
            raise UserError(_('This action is only for Access tickets'))
        
        self.state = 'cancelled'
        self.message_post(body=_('Access request cancelled'))
        return True

    # ===== PURCHASE WORKFLOW =====
    
    def action_purchase_submit(self):
        """Submit purchase request"""
        self.ensure_one()
        if self.category != 'purchase':
            raise UserError(_('This action is only for Purchase tickets'))
        if self.state != 'draft':
            raise UserError(_('Only draft tickets can be submitted'))
        
        if not self.purchase_line_ids:
            raise ValidationError(_('Please add at least one purchase item'))
        
        self.state = 'waiting_manager'
        self._set_sla_policy()
        
        # Send to manager for approval
        if self.manager_id and self.manager_id.user_id:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=_('Purchase Request Approval: %s') % self.name,
                note=_('A purchase request requires your approval.\n\n%s') % (self.description or ''),
                user_id=self.manager_id.user_id.id
            )
        
        self.message_post(body=_('Purchase request submitted and waiting for manager approval'))
        return True

    def action_purchase_manager_approve(self):
        """Manager approves purchase request"""
        self.ensure_one()
        if self.category != 'purchase':
            raise UserError(_('This action is only for Purchase tickets'))
        if self.state != 'waiting_manager':
            raise UserError(_('Only tickets waiting for manager approval can be approved'))
        
        self.state = 'waiting_it'
        
        # Send to IT team
        if self.it_responsible_id:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=_('Purchase Request Approved: %s') % self.name,
                note=_('Purchase request has been approved. Please review and create PO if needed.'),
                user_id=self.it_responsible_id.id
            )
        
        self.message_post(body=_('Purchase request approved by manager'))
        return True

    def action_purchase_manager_reject(self):
        """Manager rejects purchase request"""
        self.ensure_one()
        if self.category != 'purchase':
            raise UserError(_('This action is only for Purchase tickets'))
        if self.state != 'waiting_manager':
            raise UserError(_('Only tickets waiting for manager approval can be rejected'))
        
        self.state = 'rejected'
        self.message_post(body=_('Purchase request rejected by manager'))
        return True

    def action_purchase_create_po(self):
        """Create purchase order from ticket lines"""
        self.ensure_one()
        if self.category != 'purchase':
            raise UserError(_('This action is only for Purchase tickets'))
        if self.state != 'waiting_it':
            raise UserError(_('Only tickets waiting for IT approval can create PO'))
        
        if not self.purchase_line_ids:
            raise ValidationError(_('No purchase lines found to create PO'))
        
        # Find vendor
        vendor = self.env['res.partner'].search([('supplier_rank', '>', 0)], limit=1)
        if not vendor:
            # Use base demo vendor
            vendor = self.env.ref('base.res_partner_1', raise_if_not_found=False) or \
                    self.env.ref('base.res_partner_4', raise_if_not_found=False)
        
        if not vendor:
            raise UserError(_('No vendor found. Please create a vendor first.'))
        
        po_lines = []
        for line in self.purchase_line_ids:
            po_lines.append((0, 0, {
                'product_id': line.product_id.id if line.product_id else None,
                'name': line.name,
                'product_qty': line.quantity,
                'product_uom': line.uom_id.id if line.uom_id else self.env.ref('uom.product_uom_unit').id,
                'price_unit': line.estimated_cost or 0.0,
                'date_planned': fields.Datetime.now(),
            }))
        
        po_vals = {
            'partner_id': vendor.id,
            'origin': self.name,
            'company_id': self.company_id.id,
            'order_line': po_lines,
            'notes': self.description or '',
        }
        
        po = self.env['purchase.order'].create(po_vals)
        self.purchase_id = po
        self.state = 'po_created'
        self._record_response_time()
        
        self.message_post(body=_('Purchase Order %s created') % po.name)
        return {
            'name': _('Purchase Order'),
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'res_id': po.id,
            'view_mode': 'form',
        }

    def action_purchase_mark_received(self):
        """Mark items as received"""
        self.ensure_one()
        if self.category != 'purchase':
            raise UserError(_('This action is only for Purchase tickets'))
        if self.state != 'po_created':
            raise UserError(_('Only tickets with PO created can be marked as received'))
        
        self.state = 'received'
        self.message_post(body=_('Items received'))
        return True

    def action_purchase_close(self):
        """Close purchase request"""
        self.ensure_one()
        if self.category != 'purchase':
            raise UserError(_('This action is only for Purchase tickets'))
        if self.state not in ['received', 'po_created']:
            raise UserError(_('Only received or PO created tickets can be closed'))
        
        self._record_resolve_time()
        self.state = 'closed'
        
        # Notify requester
        if self.employee_id and self.employee_id.user_id:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=_('Purchase Closed: %s') % self.name,
                note=_('Your purchase request has been completed.'),
                user_id=self.employee_id.user_id.id
            )
        
        self.message_post(body=_('Purchase request closed'))
        return True

    def action_purchase_cancel(self):
        """Cancel purchase request"""
        self.ensure_one()
        if self.category != 'purchase':
            raise UserError(_('This action is only for Purchase tickets'))
        
        if self.purchase_id:
            self.purchase_id.button_cancel()
        
        self.state = 'cancelled'
        self.message_post(body=_('Purchase request cancelled'))
        return True

    # SLA methods
    def _set_sla_policy(self):
        """Set SLA policy and deadline based on category and SLA level"""
        self.ensure_one()
        sla_policy = self.env['it.sla.policy'].get_sla_policy(
            self.category, self.sla_level
        )
        if sla_policy:
            self.sla_policy_id = sla_policy
            self.deadline_sla = fields.Datetime.now() + timedelta(hours=sla_policy.resolve_time_hours)

    def _record_response_time(self):
        """Record response time when ticket is first responded to"""
        self.ensure_one()
        if not self.responded_at:
            self.responded_at = fields.Datetime.now()
            if self.create_date:
                delta = self.responded_at - self.create_date
                self.ttr_respond = delta.total_seconds() / 3600

    def _record_resolve_time(self):
        """Record resolve time when ticket is resolved"""
        self.ensure_one()
        self.resolved_at = fields.Datetime.now()
        if self.create_date:
            delta = self.resolved_at - self.create_date
            self.ttr_resolve = delta.total_seconds() / 3600

    @api.model
    def check_sla_breaches(self):
        """Scheduled method to check for SLA breaches"""
        now = fields.Datetime.now()
        breached_tickets = self.search([
            ('deadline_sla', '<', now),
            ('state', 'not in', ['closed', 'cancelled', 'resolved']),
            ('sla_breached', '=', False)
        ])
        
        for ticket in breached_tickets:
            ticket.sla_breached = True
            ticket.message_post(body=_('SLA breached!'))

    # ISO printing methods
    def action_print_iso_report(self):
        """Print ISO report and update tracking"""
        self.ensure_one()
        self.printed_count += 1
        self.printed_by = self.env.user
        self.printed_at = fields.Datetime.now()
        
        if self.category == 'issue':
            return self.env.ref('buz_it_ticket.action_report_it_issue').report_action(self)
        elif self.category == 'access':
            return self.env.ref('buz_it_ticket.action_report_it_access_request').report_action(self)
        elif self.category == 'purchase':
            return self.env.ref('buz_it_ticket.action_report_it_purchase_request').report_action(self)
        
        return False

    # Override methods for access template
    @api.onchange('access_template_id')
    def _onchange_access_template_id(self):
        """Load access lines from template"""
        if self.access_template_id:
            # Clear existing lines
            self.access_line_ids = [(5, 0, 0)]
            
            # Add lines from template
            for template_line in self.access_template_id.line_ids:
                self.access_line_ids = [(0, 0, {
                    'name': template_line.name,
                    'access_type': template_line.access_type,
                    'access_payload': template_line.access_payload,
                    'notes': template_line.notes,
                })]

    def action_record_print(self):
        """Record printing details and generate report"""
        self.ensure_one()
        self.printed_count += 1
        self.printed_by = self.env.user.id
        self.printed_at = fields.Datetime.now()
        
        # Return the appropriate report based on category
        if self.category == 'issue':
            return self.env.ref('buz_it_ticket.action_report_it_issue').report_action(self)
        elif self.category == 'access':
            return self.env.ref('buz_it_ticket.action_report_it_access_request').report_action(self)
        elif self.category == 'purchase':
            return self.env.ref('buz_it_ticket.action_report_it_purchase_request').report_action(self)
        
        return False

    def action_view_activities(self):
        """View activities for this ticket"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Activities',
            'res_model': 'mail.activity',
            'view_mode': 'tree,form',
            'domain': [('res_model', '=', 'it.ticket'), ('res_id', '=', self.id)],
            'context': {'default_res_model': 'it.ticket', 'default_res_id': self.id},
        }

    def action_view_purchase_order(self):
        """View purchase order for this ticket"""
        self.ensure_one()
        if not self.purchase_id:
            raise UserError(_('No Purchase Order found for this ticket'))
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Purchase Order',
            'res_model': 'purchase.order',
            'res_id': self.purchase_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def get_form_view_id(self):
        """Return the appropriate form view ID based on ticket category"""
        self.ensure_one()
        if self.category == 'issue':
            return self.env.ref('buz_it_ticket.view_it_ticket_issue_form').id
        elif self.category == 'access':
            return self.env.ref('buz_it_ticket.view_it_ticket_access_form').id
        elif self.category == 'purchase':
            return self.env.ref('buz_it_ticket.view_it_ticket_purchase_form').id
        return False