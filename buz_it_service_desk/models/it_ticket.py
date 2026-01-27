# -*- coding: utf-8 -*-

from datetime import datetime, timedelta
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class ITTicket(models.Model):
    _name = 'it.ticket'
    _description = 'IT Ticket'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'
    _rec_name = 'name'

    name = fields.Char(string='Ticket Number', required=True, readonly=True, copy=False, default='New')
    subject = fields.Char(string='Subject', required=True, tracking=True)
    description = fields.Text(string='Description', tracking=True)
    ticket_type = fields.Selection([
        ('incident', 'Incident'),
        ('service', 'Service Request'),
        ('purchase', 'Purchase Request'),
    ], string='Ticket Type', required=True, default='incident', tracking=True)
    
    category_id = fields.Many2one('it.category', string='Category', tracking=True)
    priority = fields.Selection([
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ], string='Priority', required=True, default='medium', tracking=True)
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('in_progress', 'In Progress'),
        ('waiting', 'Waiting'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
    ], string='State', default='draft', tracking=True)
    
    requester_id = fields.Many2one('res.users', string='Requester', required=True, 
                                   default=lambda self: self.env.user, tracking=True)
    assigned_to_id = fields.Many2one('res.users', string='Assigned To', tracking=True)
    department_id = fields.Many2one('hr.department', string='Department', tracking=True)
    
    # SLA related fields
    sla_deadline = fields.Datetime(string='SLA Deadline', tracking=True)
    close_date = fields.Datetime(string='Close Date', readonly=True)
    
    # Incident specific fields
    asset_tag = fields.Char(string='Asset Tag', tracking=True)
    serial_no = fields.Char(string='Serial Number', tracking=True)
    impact_level = fields.Selection([
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ], string='Impact Level', tracking=True)
    
    # Counters for smart buttons
    service_request_count = fields.Integer(compute='_compute_service_request_count')
    purchase_request_count = fields.Integer(compute='_compute_purchase_request_count')
    
    @api.depends('ticket_type')
    def _compute_service_request_count(self):
        for ticket in self:
            if ticket.ticket_type == 'service':
                ticket.service_request_count = self.env['it.service.request'].search_count([
                    ('ticket_id', '=', ticket.id)
                ])
            else:
                ticket.service_request_count = 0
    
    @api.depends('ticket_type')
    def _compute_purchase_request_count(self):
        for ticket in self:
            if ticket.ticket_type == 'purchase':
                ticket.purchase_request_count = self.env['it.purchase.request'].search_count([
                    ('ticket_id', '=', ticket.id)
                ])
            else:
                ticket.purchase_request_count = 0
    
    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('it.ticket.sequence') or 'New'
        
        ticket = super(ITTicket, self).create(vals)
        
        # Set SLA deadline based on priority
        if ticket.priority:
            ticket._set_sla_deadline()
        
        # Auto-submit if not draft
        if ticket.state != 'draft':
            ticket.action_submit()
            
        return ticket
    
    def write(self, vals):
        # Update SLA deadline if priority changed
        if 'priority' in vals:
            for ticket in self:
                old_priority = ticket.priority
                new_priority = vals['priority']
                if old_priority != new_priority:
                    ticket._set_sla_deadline()
        
        # Set close date when ticket is done
        if 'state' in vals and vals['state'] == 'done':
            vals['close_date'] = fields.Datetime.now()
        
        return super(ITTicket, self).write(vals)
    
    def _set_sla_deadline(self):
        """Set SLA deadline based on ticket priority"""
        sla = self.env['it.sla'].get_sla_by_priority(self.priority)
        if sla:
            self.sla_deadline = fields.Datetime.now() + timedelta(hours=sla.resolve_time)
            
            # Schedule warning activity
            if sla.warning_time > 0:
                warning_date = fields.Datetime.now() + timedelta(hours=sla.warning_time)
                activity_type = self.env.ref('buz_it_service_desk.mail_activity_sla_warning')
                if activity_type:
                    self.activity_schedule(
                        activity_type.id,
                        deadline=warning_date,
                        summary=_('SLA Warning: %s', self.name),
                        note=_('Ticket %s is approaching SLA deadline') % self.name
                    )
    
    def action_submit(self):
        """Submit the ticket"""
        self.write({'state': 'submitted'})
        self.message_post(body=_("Ticket submitted"))
        
        # Auto-assign if category has default team
        if self.category_id and self.category_id.team_id:
            self.write({'assigned_to_id': self.category_id.team_id.id})
    
    def action_assign_to_me(self):
        """Assign ticket to current user"""
        self.write({'assigned_to_id': self.env.user.id, 'state': 'in_progress'})
        self.message_post(body=_("Ticket assigned to %s") % self.env.user.name)
    
    def action_in_progress(self):
        """Set ticket to in progress"""
        self.write({'state': 'in_progress'})
        self.message_post(body=_("Ticket is now in progress"))
    
    def action_waiting(self):
        """Set ticket to waiting"""
        self.write({'state': 'waiting'})
        self.message_post(body=_("Ticket is waiting for response"))
    
    def action_done(self):
        """Set ticket to done"""
        self.write({'state': 'done', 'close_date': fields.Datetime.now()})
        self.message_post(body=_("Ticket completed"))
    
    def action_cancel(self):
        """Cancel the ticket"""
        self.write({'state': 'cancel'})
        self.message_post(body=_("Ticket cancelled"))
    
    def action_draft(self):
        """Reset ticket to draft"""
        self.write({'state': 'draft'})
        self.message_post(body=_("Ticket reset to draft"))
    
    def action_view_service_request(self):
        """View service request related to this ticket"""
        self.ensure_one()
        action = self.env.ref('buz_it_service_desk.action_it_service_request').read()[0]
        action['domain'] = [('ticket_id', '=', self.id)]
        return action
    
    def action_view_purchase_request(self):
        """View purchase request related to this ticket"""
        self.ensure_one()
        action = self.env.ref('buz_it_service_desk.action_it_purchase_request').read()[0]
        action['domain'] = [('ticket_id', '=', self.id)]
        return action
    
    def create_service_request(self):
        """Create a service request for this ticket"""
        self.ensure_one()
        if self.ticket_type != 'service':
            raise UserError(_("Only service type tickets can have service requests"))
        
        return {
            'name': _('Create Service Request'),
            'type': 'ir.actions.act_window',
            'res_model': 'it.service.request',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_ticket_id': self.id,
                'default_requester_id': self.requester_id.id,
            }
        }
    
    def create_purchase_request(self):
        """Create a purchase request for this ticket"""
        self.ensure_one()
        if self.ticket_type != 'purchase':
            raise UserError(_("Only purchase type tickets can have purchase requests"))
        
        return {
            'name': _('Create Purchase Request'),
            'type': 'ir.actions.act_window',
            'res_model': 'it.purchase.request',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_ticket_id': self.id,
                'default_requester_id': self.requester_id.id,
            }
        }
    
    @api.onchange('requester_id')
    def _onchange_requester_id(self):
        """Set department based on requester"""
        if self.requester_id and self.requester_id.employee_id:
            self.department_id = self.requester_id.employee_id.department_id.id