# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class JobNote(models.Model):
    _name = 'job.note'
    _description = 'Job Note'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(string='Subject', required=True)
    
    # Relations
    project_id = fields.Many2one('project.project', string='Project')
    job_order_id = fields.Many2one('job.order', string='Job Order')
    
    # Note details
    note_type = fields.Selection([
        ('general', 'General Note'),
        ('progress', 'Progress Update'),
        ('issue', 'Issue/Problem'),
        ('solution', 'Solution'),
        ('meeting', 'Meeting Minutes'),
        ('instruction', 'Instruction'),
        ('observation', 'Observation')
    ], string='Note Type', default='general', required=True)
    
    description = fields.Html(string='Description', required=True)
    date = fields.Datetime(string='Date', default=fields.Datetime.now, required=True)
    
    # Assignment
    user_id = fields.Many2one('res.users', string='Created by', default=lambda self: self.env.user, required=True)
    assigned_to_ids = fields.Many2many('res.users', string='Assigned To')
    
    # Priority and status
    priority = fields.Selection([
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('urgent', 'Urgent')
    ], string='Priority', default='normal')
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('resolved', 'Resolved'),
        ('archived', 'Archived')
    ], string='Status', default='draft', tracking=True)
    
    # Attachments and references
    attachment_ids = fields.Many2many('ir.attachment', string='Attachments')
    reference = fields.Char(string='Reference')
    
    # Follow-up
    follow_up_date = fields.Date(string='Follow-up Date')
    follow_up_note_id = fields.Many2one('job.note', string='Follow-up Note')
    parent_note_id = fields.Many2one('job.note', string='Parent Note')
    child_note_ids = fields.One2many('job.note', 'parent_note_id', string='Follow-up Notes')
    
    # Tags
    tag_ids = fields.Many2many('job.note.tag', string='Tags')
    
    # Visibility
    is_private = fields.Boolean(string='Private', default=False,
                               help='If checked, only the creator and assigned users can see this note')
    
    # Other fields
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    active = fields.Boolean(string='Active', default=True)
    
    def action_activate(self):
        self.write({'state': 'active'})
    
    def action_resolve(self):
        self.write({'state': 'resolved'})
    
    def action_archive(self):
        self.write({'state': 'archived', 'active': False})
    
    def action_create_follow_up(self):
        return {
            'name': 'Create Follow-up Note',
            'type': 'ir.actions.act_window',
            'res_model': 'job.note',
            'view_mode': 'form',
            'context': {
                'default_parent_note_id': self.id,
                'default_project_id': self.project_id.id,
                'default_job_order_id': self.job_order_id.id,
                'default_name': f'Follow-up: {self.name}',
                'default_note_type': 'general'
            },
            'target': 'new'
        }


class JobNoteTag(models.Model):
    _name = 'job.note.tag'
    _description = 'Job Note Tag'
    _order = 'name'

    name = fields.Char(string='Tag Name', required=True)
    color = fields.Integer(string='Color')
    description = fields.Text(string='Description')
    active = fields.Boolean(string='Active', default=True)
    
    _sql_constraints = [
        ('name_uniq', 'unique (name)', 'Tag name must be unique!')
    ]
