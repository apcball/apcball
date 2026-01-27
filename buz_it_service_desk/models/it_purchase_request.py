# -*- coding: utf-8 -*-

from datetime import datetime, timedelta
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class ITPurchaseRequest(models.Model):
    _name = 'it.purchase.request'
    _description = 'IT Purchase Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'request_date desc'
    _rec_name = 'name'

    # Header Fields
    name = fields.Char(string='Document Number', required=True, readonly=True, copy=False, default='New')
    request_date = fields.Date(string='Request Date', required=True, default=fields.Date.today, tracking=True)
    requester_id = fields.Many2one('res.users', string='Requester', required=True, 
                                   default=lambda self: self.env.user, tracking=True)
    department_id = fields.Many2one('hr.department', string='Department', tracking=True)
    
    # Equipment Request Lines
    line_ids = fields.One2many('it.purchase.request.line', 'request_id', string='Equipment Items', copy=True)
    
    # Workflow fields
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('manager_approved', 'Manager Approved'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
    ], string='State', default='draft', tracking=True)
    
    # Approval Fields
    manager_approved_by = fields.Many2one('res.users', string='Approved by Manager', readonly=True, tracking=True)
    manager_approved_date = fields.Date(string='Manager Approval Date', readonly=True, tracking=True)
    it_received_by = fields.Many2one('res.users', string='IT Received by', readonly=True, tracking=True)
    it_received_date = fields.Date(string='IT Received Date', readonly=True, tracking=True)
    
    @api.constrains('line_ids')
    def _check_line_ids(self):
        for request in self:
            if not request.line_ids:
                raise ValidationError(_('At least one equipment item is required'))
    
    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('it.purchase.request.sequence') or 'New'
        
        request = super(ITPurchaseRequest, self).create(vals)
        return request
    
    def action_submit(self):
        """Submit the purchase request"""
        self.write({'state': 'submitted'})
        self.message_post(body=_("Purchase request submitted for manager approval"))
    
    def action_manager_approve(self):
        """Manager approves the request"""
        self.write({
            'state': 'manager_approved',
            'manager_approved_date': fields.Date.today(),
            'manager_approved_by': self.env.user.id
        })
        self.message_post(body=_("Purchase request approved by manager"))
    
    def action_complete(self):
        """Complete the purchase request"""
        self.write({
            'state': 'done',
            'it_received_date': fields.Date.today(),
            'it_received_by': self.env.user.id
        })
        self.message_post(body=_("Purchase request completed"))
    
    def action_cancel(self):
        """Cancel the request"""
        self.write({'state': 'cancel'})
        self.message_post(body=_("Purchase request cancelled"))
    
    def action_draft(self):
        """Reset request to draft"""
        self.write({
            'state': 'draft',
            'manager_approved_date': False,
            'manager_approved_by': False,
            'it_received_date': False,
            'it_received_by': False
        })
        self.message_post(body=_("Purchase request reset to draft"))


class ITPurchaseRequestLine(models.Model):
    _name = 'it.purchase.request.line'
    _description = 'IT Purchase Request Line'
    _order = 'sequence, id'

    request_id = fields.Many2one('it.purchase.request', string='Request', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=1)
    
    item_name = fields.Char(string='Item Name', required=True, tracking=True)
    item_type = fields.Char(string='Item Type', required=True, tracking=True)
    cost_center_code = fields.Char(string='Cost Center Code', tracking=True)
    change_reason = fields.Text(string='Change Reason', tracking=True)