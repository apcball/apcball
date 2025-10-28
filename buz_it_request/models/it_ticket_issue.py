from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import datetime, timedelta
import pytz


class ITTicketIssue(models.Model):
    _name = 'it.ticket.issue'
    _description = 'IT Ticket Issue - For reporting IT problems'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'issue_date desc'
    
    active = fields.Boolean(default=True)

    name = fields.Char('Ticket Number', required=True, copy=False, readonly=True, 
                       default=lambda self: _('New'))
    requester_id = fields.Many2one('hr.employee', string='Requester', required=True,
                                   default=lambda self: self.env.user.employee_id)
    department_id = fields.Many2one('hr.department', string='Department', 
                                    related='requester_id.department_id', store=True)
    location_id = fields.Many2one('hr.work.location', string='Location',
                                  related='requester_id.work_location_id', store=True)
    category_id = fields.Many2one('it.category', string='Category', required=True,
                                  help="Category of the IT issue (computer, printer, network, software, other)")
    priority = fields.Selection([
        ('0', 'Low'),
        ('1', 'Normal'),
        ('2', 'High'),
        ('3', 'Urgent')
    ], string='Priority', default='1', required=True)
    issue_date = fields.Datetime('Issue Date', default=fields.Datetime.now, required=True)
    due_date = fields.Datetime('Due Date', compute='_compute_due_date', store=True)
    resolved_date = fields.Datetime('Resolved Date')
    description = fields.Text('Description', required=True)
    attachment_ids = fields.Many2many('ir.attachment', string='Attachments')
    
    assignee_id = fields.Many2one('hr.employee', string='Assigned Technician')
    root_cause = fields.Text('Root Cause')
    resolution_note = fields.Text('Resolution Note')
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('triage', 'Triage'),
        ('in_progress', 'In Progress'),
        ('waiting_user', 'Waiting User'),
        ('done', 'Done'),
        ('cancel', 'Cancelled')
    ], string='State', default='draft', tracking=True)
    
    sla_status = fields.Selection([
        ('on_track', 'On Track'),
        ('risk', 'At Risk'),
        ('breached', 'Breached')
    ], string='SLA Status', compute='_compute_sla_status', store=True)

    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('it.ticket.issue') or _('New')
        return super().create(vals)

    @api.model
    def _get_it_employees(self):
        """Get employees from IT department"""
        it_department = self.env.ref('hr.dep_it', False)
        if it_department:
            return self.env['hr.employee'].search([('department_id', '=', it_department.id)]).ids
        return []

    @api.depends('priority', 'issue_date')
    def _compute_due_date(self):
        """Calculate due date based on SLA policy"""
        for ticket in self:
            if ticket.issue_date and ticket.priority:
                # Get SLA policy for priority
                sla_policy = self.env['it.sla.policy'].search([('priority', '=', ticket.priority)], limit=1)
                if sla_policy:
                    # Calculate due date based on business hours if working calendar is available
                    issue_datetime = fields.Datetime.from_string(ticket.issue_date)
                    # Simple calculation: add SLA hours to issue datetime
                    due_datetime = issue_datetime + timedelta(hours=sla_policy.resolution_hours)
                    ticket.due_date = due_datetime
                else:
                    ticket.due_date = ticket.issue_date + timedelta(hours=24)  # Default 24 hours
            else:
                ticket.due_date = False

    @api.depends('issue_date', 'resolved_date', 'due_date')
    def _compute_sla_status(self):
        """Compute SLA status based on due date and resolution time"""
        for ticket in self:
            if ticket.state == 'done':
                if ticket.resolved_date and ticket.due_date:
                    if ticket.resolved_date <= ticket.due_date:
                        ticket.sla_status = 'on_track'
                    else:
                        ticket.sla_status = 'breached'
                else:
                    ticket.sla_status = 'on_track'  # If dates are missing, assume on track
            elif ticket.due_date:
                # Check if ticket is at risk of breaching SLA
                current_time = fields.Datetime.now()
                sla_policy = self.env['it.sla.policy'].search([('priority', '=', ticket.priority)], limit=1)
                
                if current_time > ticket.due_date:
                    ticket.sla_status = 'breached'
                elif sla_policy and current_time > (ticket.due_date - timedelta(hours=sla_policy.warning_hours)):
                    ticket.sla_status = 'risk'
                else:
                    ticket.sla_status = 'on_track'
            else:
                ticket.sla_status = 'on_track'

    def action_triage(self):
        """Move ticket to triage state"""
        self.write({'state': 'triage'})
        # Auto-assign based on category
        self._action_auto_assign()

    def action_start_progress(self):
        """Move ticket to in progress state"""
        self.write({'state': 'in_progress'})

    def action_wait_user(self):
        """Move ticket to waiting user state"""
        self.write({'state': 'waiting_user'})

    def action_resolve(self):
        """Resolve the ticket"""
        if not self.resolution_note:
            raise ValidationError(_("Resolution note is required to close the ticket."))
        self.write({
            'state': 'done',
            'resolved_date': fields.Datetime.now()
        })

    def action_cancel(self):
        """Cancel the ticket"""
        self.write({'state': 'cancel'})

    def _action_auto_assign(self):
        """Auto-assign technician based on category"""
        # This is a simplified assignment logic
        # In a real implementation, you might have more complex assignment rules
        for ticket in self:
            if not ticket.assignee_id:
                # Find IT employees associated with this category
                # For now, just assign to the first available IT employee
                it_employees = self.env['hr.employee'].search([
                    ('id', 'in', self._get_it_employees())
                ], limit=1)
                if it_employees:
                    ticket.assignee_id = it_employees[0]