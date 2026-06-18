# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class ITRequest(models.Model):
    _name = 'it.request'
    _description = 'IT Request'
    _order = 'create_date desc'
    _rec_name = 'name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # Identity / Number
    name = fields.Char(
        string='Request Number',
        required=True, readonly=True, copy=False,
        default='New',
    )
    subject = fields.Char(string='Subject', required=True, tracking=True)
    description = fields.Text(string='Description', tracking=True)

    # Categorization
    request_type = fields.Selection(
        selection=[
            ('dev_feature', 'Dev / Feature Request'),
            ('error', 'Error / Bug Report'),
            ('equipment_repair', 'Equipment Repair'),
        ],
        string='Request Type',
        required=True,
        default='dev_feature',
        tracking=True,
    )
    priority = fields.Selection(
        selection=[
            ('low', 'Low'),
            ('medium', 'Medium'),
            ('high', 'High'),
            ('critical', 'Critical'),
        ],
        string='Priority',
        default='medium',
        tracking=True,
    )

    # State / Workflow
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('submitted', 'Submitted'),
            ('in_progress', 'In Progress'),
            ('waiting', 'Waiting'),
            ('done', 'Done'),
            ('cancel', 'Cancelled'),
        ],
        string='State',
        default='draft',
        tracking=True,
    )

    # Parties / Assignment
    requester_id = fields.Many2one(
        comodel_name='res.users',
        string='Requester',
        required=True,
        default=lambda self: self.env.user,
        tracking=True,
    )
    assigned_to_id = fields.Many2one(
        comodel_name='res.users',
        string='Assigned To',
        tracking=True,
    )
    department_id = fields.Many2one(
        comodel_name='hr.department',
        string='Department',
        tracking=True,
    )

    # Resolution
    close_date = fields.Datetime(string='Close Date', readonly=True)

    # Type-specific: equipment_repair
    asset_tag = fields.Char(string='Asset Tag', tracking=True)
    serial_no = fields.Char(string='Serial No.', tracking=True)
    location = fields.Char(string='Location', tracking=True)
    reported_symptom = fields.Text(string='Reported Symptom', tracking=True)

    # Type-specific: error
    affected_system = fields.Char(string='Affected System', tracking=True)
    error_message = fields.Text(string='Error Message', tracking=True)
    repro_steps = fields.Text(string='Reproduction Steps', tracking=True)

    # Type-specific: dev_feature
    target_module = fields.Char(string='Target Module', tracking=True)
    requested_feature = fields.Text(string='Requested Feature', tracking=True)

    # ---- CRUD ----
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('it.request.sequence') or 'New'
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('state') == 'done' and not vals.get('close_date'):
            vals['close_date'] = fields.Datetime.now()
        return super().write(vals)

    # ---- Onchange ----
    @api.onchange('requester_id')
    def _onchange_requester_id(self):
        if self.requester_id and self.requester_id.employee_id:
            self.department_id = self.requester_id.employee_id.department_id.id

    # ---- Workflow actions ----
    def action_submit(self):
        self.write({'state': 'submitted'})
        for rec in self:
            rec.message_post(body=_('Request %s has been submitted.') % rec.name)

    def action_assign_to_me(self):
        self.write({'assigned_to_id': self.env.user.id, 'state': 'in_progress'})
        for rec in self:
            rec.message_post(body=_('Request %s assigned to %s.') % (rec.name, self.env.user.name))

    def action_in_progress(self):
        self.write({'state': 'in_progress'})

    def action_waiting(self):
        self.write({'state': 'waiting'})

    def action_done(self):
        self.write({'state': 'done'})
        for rec in self:
            rec.message_post(body=_('Request %s has been completed.') % rec.name)

    def action_cancel(self):
        self.write({'state': 'cancel'})
        for rec in self:
            rec.message_post(body=_('Request %s has been cancelled.') % rec.name)

    def action_draft(self):
        self.write({'state': 'draft', 'close_date': False})