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
    
    description = fields.Html(string='Description')
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
    
    def _notify_get_groups(self):
        """Override to disable email notifications - only use activities"""
        return []
    
    def _notify_get_recipients(self):
        """Override to disable email notifications - only use activities"""
        return []
    
    def _notify_thread(self, message, msg_vals=False, **kwargs):
        """Override to disable email notifications - only use activities"""
        # Do not send any email notifications
        return super(JobNote, self)._notify_thread(message, msg_vals, send_after_commit=False, **kwargs)
    
    def action_activate(self):
        self.write({'state': 'active'})
        # Create activity for assigned users
        self._create_activity_for_assigned_users('Note Activated', 'This job note has been activated and requires attention.')
    
    def action_resolve(self):
        self.write({'state': 'resolved'})
        # Create activity for creator
        self._create_activity_for_creator('Note Resolved', 'Your job note has been resolved.')
    
    def action_archive(self):
        self.write({'state': 'archived', 'active': False})
    
    def _create_activity_for_assigned_users(self, summary, note):
        """Create activity for assigned users"""
        if self.assigned_to_ids:
            try:
                # Find a suitable activity type
                activity_type = self.env['mail.activity.type'].search([
                    ('category', '=', 'default')
                ], limit=1)
                
                if not activity_type:
                    activity_type = self.env['mail.activity.type'].search([], limit=1)
                
                if activity_type:
                    for user in self.assigned_to_ids:
                        self.activity_schedule(
                            activity_type_id=activity_type.id,
                            summary=summary,
                            note=note,
                            user_id=user.id,
                            date_deadline=fields.Date.today()
                        )
            except Exception:
                # If activity creation fails, continue silently
                pass
    
    def _create_activity_for_creator(self, summary, note):
        """Create activity for note creator"""
        try:
            # Find a suitable activity type
            activity_type = self.env['mail.activity.type'].search([
                ('category', '=', 'default')
            ], limit=1)
            
            if not activity_type:
                activity_type = self.env['mail.activity.type'].search([], limit=1)
            
            if activity_type:
                self.activity_schedule(
                    activity_type_id=activity_type.id,
                    summary=summary,
                    note=note,
                    user_id=self.user_id.id,
                    date_deadline=fields.Date.today()
                )
        except Exception:
            # If activity creation fails, continue silently
            pass
    
    @api.model
    def create(self, vals):
        """Override create to create activity notification without email"""
        result = super(JobNote, self).create(vals)
        
        # Create activity for assigned users when note is created
        if result.assigned_to_ids and result.state == 'draft':
            result._create_activity_for_assigned_users(
                f'New Job Note: {result.name}',
                f'A new job note has been created and assigned to you: {result.name}'
            )
        
        return result

    def write(self, vals):
        """Override write to create activity notifications without email"""
        result = super(JobNote, self).write(vals)
        
        # Create activity when note is assigned to new users
        if 'assigned_to_ids' in vals and vals.get('assigned_to_ids'):
            for record in self:
                if record.assigned_to_ids:
                    record._create_activity_for_assigned_users(
                        f'Job Note Assigned: {record.name}',
                        f'You have been assigned to job note: {record.name}'
                    )
        
        return result
    
    def action_create_follow_up(self):
        follow_up = self.env['job.note'].create({
            'parent_note_id': self.id,
            'project_id': self.project_id.id,
            'job_order_id': self.job_order_id.id,
            'name': f'Follow-up: {self.name}',
            'note_type': 'general',
            'description': f'<p>Follow-up note for: <a href="#" data-oe-model="job.note" data-oe-id="{self.id}">{self.name}</a></p>',
            'assigned_to_ids': [(6, 0, self.assigned_to_ids.ids)]
        })
        
        # Create activity for follow-up
        if self.assigned_to_ids:
            try:
                activity_type = self.env['mail.activity.type'].search([('name', 'ilike', 'to do')], limit=1)
                if not activity_type:
                    activity_type = self.env['mail.activity.type'].search([], limit=1)
                
                if activity_type:
                    for user in self.assigned_to_ids:
                        follow_up.activity_schedule(
                            activity_type_id=activity_type.id,
                            summary=f'Follow-up: {self.name}',
                            note=f'Please follow up on the job note: {self.name}',
                            user_id=user.id,
                            date_deadline=self.follow_up_date or fields.Date.today()
                        )
            except Exception:
                # If activity creation fails, continue silently
                pass
        
        return {
            'name': 'Follow-up Note',
            'type': 'ir.actions.act_window',
            'res_model': 'job.note',
            'view_mode': 'form',
            'res_id': follow_up.id,
            'target': 'current'
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
