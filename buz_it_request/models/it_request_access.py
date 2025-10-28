from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ITRequestAccess(models.Model):
    _name = 'it.request.access'
    _description = 'IT Access Request - For requesting system access'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'
    
    active = fields.Boolean(default=True)

    name = fields.Char('Request Number', required=True, copy=False, readonly=True, 
                       default=lambda self: _('New'))
    requester_id = fields.Many2one('hr.employee', string='Requester', required=True,
                                   default=lambda self: self.env.user.employee_id)
    employee_id = fields.Many2one('hr.employee', string='Employee Receiving Access')
    department_id = fields.Many2one('hr.department', string='Department', 
                                    related='requester_id.department_id', store=True)
    request_type = fields.Selection([
        ('email', 'Email Account'),
        ('erp', 'ERP System Access'),
        ('vpn', 'VPN Access'),
        ('wifi', 'Wi-Fi Access'),
        ('shared_folder', 'Shared Folder Access'),
        ('other', 'Other')
    ], string='Request Type', required=True)
    system_detail = fields.Char('System Details')
    justification = fields.Text('Justification', required=True)
    attachment_ids = fields.Many2many('ir.attachment', string='Attachments')
    
    manager_id = fields.Many2one('hr.employee', string='Approving Manager',
                                 related='requester_id.parent_id', store=True)
    approval_note = fields.Text('Manager Approval Note')
    
    it_operator_id = fields.Many2one('hr.employee', string='IT Operator')
    it_note = fields.Text('IT Implementation Note')
    
    # Checklist functionality would require a separate model
    checklist_ids = fields.One2many('it.access.checklist', 'request_id', string='Checklist')
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('to_manager_approve', 'To Manager Approve'),
        ('manager_approved', 'Manager Approved'),
        ('to_it', 'To IT'),
        ('it_in_progress', 'IT In Progress'),
        ('done', 'Done')
    ], string='State', default='draft', tracking=True)

    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('it.request.access') or _('New')
        return super().create(vals)

    @api.model
    def _get_it_employees(self):
        """Get employees from IT department"""
        it_department = self.env.ref('hr.dep_it', False)
        if it_department:
            return self.env['hr.employee'].search([('department_id', '=', it_department.id)]).ids
        return []

    @api.onchange('requester_id')
    def _onchange_requester_id(self):
        """Set employee_id to requester_id by default"""
        if self.requester_id and not self.employee_id:
            self.employee_id = self.requester_id

    def action_submit_for_approval(self):
        """Submit request for manager approval"""
        if not self.justification:
            raise ValidationError(_("Justification is required before submitting for approval."))
        self.write({'state': 'to_manager_approve'})
        
        # Create activity for manager
        if self.manager_id.user_id:
            self.activity_schedule(
                'buz_it_request.activity_manager_approval',
                user_id=self.manager_id.user_id.id,
                note=_('Request requires your approval')
            )

    def action_manager_approve(self):
        """Manager approves the request"""
        if not self.approval_note:
            raise ValidationError(_("Approval note is required for manager approval."))
        self.write({'state': 'manager_approved'})
        
        # Create activity for IT
        it_users = self.env['hr.employee'].search([('id', 'in', self._get_it_employees())], limit=1)
        if it_users and it_users[0].user_id:
            self.activity_schedule(
                'buz_it_request.activity_it_action',
                user_id=it_users[0].user_id.id,
                note=_('Request approved and requires IT action')
            )

    def action_manager_reject(self):
        """Manager rejects the request"""
        self.write({'state': 'draft'})  # Return to requester
        self.activity_unlink('buz_it_request.activity_manager_approval')

    def action_send_to_it(self):
        """Send approved request to IT team"""
        if self.state != 'manager_approved':
            raise ValidationError(_("Request must be manager approved before sending to IT."))
        self.write({'state': 'to_it'})
        
        # Create activity for IT
        it_users = self.env['hr.employee'].search([('id', 'in', self._get_it_employees())], limit=1)
        if it_users and it_users[0].user_id:
            self.activity_schedule(
                'buz_it_request.activity_it_action',
                user_id=it_users[0].user_id.id,
                note=_('Request ready for IT implementation')
            )

    def action_start_it_work(self):
        """IT starts working on the request"""
        self.write({'state': 'it_in_progress'})

    def action_complete_request(self):
        """Complete the access request"""
        if not self.it_note:
            raise ValidationError(_("IT implementation note is required to complete the request."))
        self.write({'state': 'done'})
        self.activity_unlink('buz_it_request.activity_it_action')