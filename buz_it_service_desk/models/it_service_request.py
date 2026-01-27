# -*- coding: utf-8 -*-

from datetime import datetime, timedelta
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class ITServiceRequest(models.Model):
    _name = 'it.service.request'
    _description = 'IT Service Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'
    _rec_name = 'name'

    name = fields.Char(string='Document Number', required=True, readonly=True, copy=False, default='New')
    requester_id = fields.Many2one('res.users', string='Requester', required=True, 
                                   default=lambda self: self.env.user, tracking=True)
    
    # ข้อมูลส่วนตัวของผู้ขอ
    fullname_th = fields.Char(string='Full Name (Thai)', required=True, tracking=True)
    fullname_en = fields.Char(string='Full Name (English)', required=True, tracking=True)
    nickname = fields.Char(string='Nickname', tracking=True)
    department_id = fields.Many2one('hr.department', string='Department', tracking=True)
    employee_code = fields.Char(string='Employee Code', tracking=True)
    job_position = fields.Char(string='Job Position', tracking=True)
    line_id = fields.Char(string='LINE ID', tracking=True)
    
    # ประเภทการขอใช้งานระบบ (เลือกได้หลายรายการ)
    request_email = fields.Boolean(string='Request Email', tracking=True)
    email_details = fields.Text(string='Email Details', tracking=True)
    
    request_odoo = fields.Boolean(string='Request Odoo System Access', tracking=True)
    odoo_access_type = fields.Selection([
        ('read', 'Read Access'),
        ('write', 'Write Access'),
        ('admin', 'Admin Access'),
    ], string='Odoo Access Type', default='read', tracking=True)
    odoo_details = fields.Text(string='Odoo Details', tracking=True)
    
    request_mgtx = fields.Boolean(string='Request MGTX System Access', tracking=True)
    mgtx_access_type = fields.Selection([
        ('read', 'Read Access'),
        ('write', 'Write Access'),
        ('admin', 'Admin Access'),
    ], string='MGTX Access Type', default='read', tracking=True)
    mgtx_details = fields.Text(string='MGTX Details', tracking=True)
    
    start_date = fields.Datetime(string='Start Date', default=fields.Datetime.now, tracking=True)
    end_date = fields.Datetime(string='End Date', tracking=True)
    approval_required = fields.Boolean(string='Approval Required', default=True, tracking=True)
    
    # Workflow fields
    state = fields.Selection([
        ('draft', 'Draft'),
        ('manager_approve', 'Manager Approval'),
        ('it_approve', 'IT Approval'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
    ], string='State', default='draft', tracking=True)
    
    manager_approval_date = fields.Datetime(string='Manager Approval Date', readonly=True)
    manager_approver_id = fields.Many2one('res.users', string='Approved by Manager', readonly=True)
    it_approval_date = fields.Datetime(string='IT Approval Date', readonly=True)
    it_approver_id = fields.Many2one('res.users', string='Approved by IT', readonly=True)
    
    manager_notes = fields.Text(string='Manager Notes')
    it_notes = fields.Text(string='IT Notes')
    
    @api.constrains('end_date', 'start_date')
    def _check_dates(self):
        for request in self:
            if request.end_date and request.start_date:
                if request.end_date < request.start_date:
                    raise ValidationError(_('End date must be after start date'))
    
    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('it.service.request.sequence') or 'New'
        
        # Auto-submit if not draft
        if vals.get('state') != 'draft':
            vals['state'] = 'draft'
        
        request = super(ITServiceRequest, self).create(vals)
        
        # Auto-submit if approval not required
        if not request.approval_required:
            request.action_submit()
            
        return request
    
    def action_submit(self):
        """Submit the service request"""
        self.write({'state': 'manager_approve'})
        self.message_post(body=_("Service request submitted for manager approval"))
        
        # Auto-approve if manager is the requester
        if self.requester_id == self.ticket_id.assigned_to_id:
            self.action_manager_approve()
    
    def action_manager_approve(self):
        """Manager approves the request"""
        self.write({
            'state': 'it_approve',
            'manager_approval_date': fields.Datetime.now(),
            'manager_approver_id': self.env.user.id
        })
        self.message_post(body=_("Service request approved by manager"))
        
        # Auto-approve if IT officer is the same as manager
        if self.env.user.has_group('buz_it_service_desk.group_it_officer'):
            self.action_it_approve()
    
    def action_manager_reject(self):
        """Manager rejects the request"""
        self.write({'state': 'cancel'})
        self.message_post(body=_("Service request rejected by manager"))
    
    def action_it_approve(self):
        """IT approves the request"""
        self.write({
            'state': 'done',
            'it_approval_date': fields.Datetime.now(),
            'it_approver_id': self.env.user.id
        })
        self.message_post(body=_("Service request approved by IT"))
        
        # Update ticket state
        if self.ticket_id.state == 'waiting':
            self.ticket_id.action_in_progress()
    
    def action_it_reject(self):
        """IT rejects the request"""
        self.write({'state': 'cancel'})
        self.message_post(body=_("Service request rejected by IT"))
    
    def action_cancel(self):
        """Cancel the request"""
        self.write({'state': 'cancel'})
        self.message_post(body=_("Service request cancelled"))
    
    def action_draft(self):
        """Reset request to draft"""
        self.write({
            'state': 'draft',
            'manager_approval_date': False,
            'manager_approver_id': False,
            'it_approval_date': False,
            'it_approver_id': False
        })
        self.message_post(body=_("Service request reset to draft"))
    
    def open_approval_wizard(self):
        """Open approval wizard"""
        self.ensure_one()
        return {
            'name': _('Approve Service Request'),
            'type': 'ir.actions.act_window',
            'res_model': 'approve.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_request_id': self.id,
                'default_request_type': 'service',
            }
        }
    
    def action_create_employee(self):
        """Create employee from service request data"""
        self.ensure_one()
        
        if not self.fullname_th:
            raise UserError(_('Please fill in Thai name before creating employee'))
        
        # Check if employee already exists
        existing_employee = self.env['hr.employee'].search([
            ('name', '=', self.fullname_th)
        ], limit=1)
        
        if existing_employee:
            raise UserError(_('Employee with name %s already exists') % self.fullname_th)
        
        # Prepare employee data
        employee_vals = {
            'name': self.fullname_th,
            'department_id': self.department_id.id if self.department_id else False,
            'job_title': self.job_position,
        }
        
        # Add optional fields if available
        if self.employee_code:
            employee_vals['barcode'] = self.employee_code
        
        if self.fullname_en:
            employee_vals['name'] = f"{self.fullname_th} / {self.fullname_en}"
        
        # Create the employee
        employee = self.env['hr.employee'].create(employee_vals)
        
        # Post message
        self.message_post(
            body=_("Employee created: %s (ID: %s)") % (employee.name, employee.id)
        )
        
        # Show notification
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Employee %s created successfully') % employee.name,
                'type': 'success',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.act_window',
                    'res_model': 'hr.employee',
                    'res_id': employee.id,
                    'view_mode': 'form',
                    'target': 'current',
                }
            }
        }