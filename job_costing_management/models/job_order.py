# -*- coding: utf-8 -*-

from odoo import models, fields, api
from datetime import date


class JobOrder(models.Model):
    _name = 'job.order'
    _description = 'Job Order'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, name'

    name = fields.Char(string='Job Order', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    
    # Relations
    project_id = fields.Many2one('project.project', string='Project', required=True)
    task_id = fields.Many2one('project.task', string='Related Task')
    stage_id = fields.Many2one('job.stage', string='Stage', 
                              default=lambda self: self.env['job.stage'].search([('is_draft', '=', True)], limit=1))
    parent_job_order_id = fields.Many2one('job.order', string='Parent Job Order')
    child_job_order_ids = fields.One2many('job.order', 'parent_job_order_id', string='Sub Job Orders')
    
    # Job details
    description = fields.Text(string='Description')
    priority = fields.Selection([
        ('0', 'Low'),
        ('1', 'Normal'),
        ('2', 'High'),
        ('3', 'Very High')
    ], string='Priority', default='1')
    job_type_id = fields.Many2one('job.type', string='Job Type')
    
    # Dates
    date_start = fields.Date(string='Start Date', default=fields.Date.today)
    date_end = fields.Date(string='End Date')
    date_deadline = fields.Date(string='Deadline')
    
    # Assignment
    user_id = fields.Many2one('res.users', string='Assigned to', default=lambda self: self.env.user)
    team_ids = fields.Many2many('hr.employee', string='Team Members')
    
    # Progress
    progress = fields.Float(string='Progress (%)', default=0.0)
    kanban_state = fields.Selection([
        ('normal', 'In Progress'),
        ('done', 'Ready'),
        ('blocked', 'Blocked')
    ], string='Kanban State', default='normal')
    
    # State
    state = fields.Selection([
        ('draft', 'Draft'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled')
    ], string='State', default='draft', tracking=True)
    
    # Costs
    job_cost_sheet_ids = fields.One2many('job.cost.sheet', 'job_order_id', string='Job Cost Sheets')
    planned_cost = fields.Float(string='Planned Cost', compute='_compute_costs', store=True)
    actual_cost = fields.Float(string='Actual Cost', compute='_compute_costs', store=True)
    cost_variance = fields.Float(string='Cost Variance', compute='_compute_cost_variance', store=True)
    cost_variance_percent = fields.Float(string='Cost Variance %', compute='_compute_cost_variance', store=True)
    
    # Material management
    material_planning_ids = fields.One2many('material.planning', 'job_order_id', string='Material Planning')
    material_consumption_ids = fields.One2many('material.consumption', 'job_order_id', string='Material Consumption')
    material_requisition_ids = fields.One2many('material.requisition', 'job_order_id', string='Material Requisitions')
    
    # Timesheets
    timesheet_ids = fields.One2many('account.analytic.line', 'job_order_id', string='Timesheets')
    
    # Notes
    job_note_ids = fields.One2many('job.note', 'job_order_id', string='Job Notes')
    
    # BOQ (Bill of Quantities)
    boq_ids = fields.One2many('boq.boq', 'job_order_id', string='Bill of Quantities')
    
    # Smart button counts
    cost_sheet_count = fields.Integer(string='Cost Sheets', compute='_compute_counts')
    timesheet_count = fields.Integer(string='Timesheets', compute='_compute_counts')
    material_requisition_count = fields.Integer(string='Material Requisitions', compute='_compute_counts')
    note_count = fields.Integer(string='Notes', compute='_compute_counts')
    boq_count = fields.Integer(string='BOQs', compute='_compute_counts')
    
    # Other fields
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    active = fields.Boolean(string='Active', default=True)
    color = fields.Integer(string='Color Index')
    
    # Deadline tracking
    days_to_deadline = fields.Integer(string='Days to Deadline', compute='_compute_days_to_deadline')
    is_overdue = fields.Boolean(string='Overdue', compute='_compute_days_to_deadline')
    
    @api.depends('job_cost_sheet_ids.total_cost', 'job_cost_sheet_ids.actual_total_cost')
    def _compute_costs(self):
        for record in self:
            record.planned_cost = sum(record.job_cost_sheet_ids.mapped('total_cost'))
            record.actual_cost = sum(record.job_cost_sheet_ids.mapped('actual_total_cost'))
    
    @api.depends('job_cost_sheet_ids', 'timesheet_ids', 'material_requisition_ids', 'job_note_ids', 'boq_ids')
    def _compute_counts(self):
        for record in self:
            record.cost_sheet_count = len(record.job_cost_sheet_ids)
            record.timesheet_count = len(record.timesheet_ids)
            record.material_requisition_count = len(record.material_requisition_ids)
            record.note_count = len(record.job_note_ids)
            record.boq_count = len(record.boq_ids)
            record.boq_count = len(record.boq_ids)
    
    @api.depends('planned_cost', 'actual_cost')
    def _compute_cost_variance(self):
        for record in self:
            if record.planned_cost:
                record.cost_variance = record.actual_cost - record.planned_cost
                record.cost_variance_percent = (record.cost_variance / record.planned_cost) * 100
            else:
                record.cost_variance = 0.0
                record.cost_variance_percent = 0.0
    
    @api.depends('date_deadline')
    def _compute_days_to_deadline(self):
        for record in self:
            if record.date_deadline:
                today = fields.Date.today()
                delta = record.date_deadline - today
                record.days_to_deadline = delta.days
                record.is_overdue = delta.days < 0
            else:
                record.days_to_deadline = 0
                record.is_overdue = False
    

    
    def action_start(self):
        """Start the job order"""
        self.write({'state': 'in_progress'})
        return True
    
    def action_done(self):
        """Mark job order as done"""
        self.write({'state': 'done', 'progress': 100.0})
        return True
    
    def action_cancel(self):
        """Cancel the job order"""
        self.write({'state': 'cancelled'})
        return True
    
    def action_reset_to_draft(self):
        """Reset job order to draft"""
        self.write({'state': 'draft', 'progress': 0.0})
        return True

    @api.model
    def create(self, vals):
        """Override create to set sequence"""
        if vals.get('name', '/') == '/':
            vals['name'] = self.env['ir.sequence'].next_by_code('job.order') or '/'
        return super(JobOrder, self).create(vals)

    def name_get(self):
        """Custom name_get to show project and job order name"""
        result = []
        for record in self:
            name = record.name
            if record.project_id:
                name = f"[{record.project_id.name}] {name}"
            result.append((record.id, name))
        return result
    
    @api.onchange('project_id')
    def _onchange_project_id(self):
        """Update domain for task_id when project changes"""
        if self.project_id:
            return {'domain': {'task_id': [('project_id', '=', self.project_id.id)]}}
        else:
            return {'domain': {'task_id': []}}
    
    @api.onchange('progress')
    def _onchange_progress(self):
        """Auto update state based on progress"""
        if self.progress == 100.0:
            self.kanban_state = 'done'
        elif self.progress > 0:
            self.kanban_state = 'normal'
        
    def copy(self, default=None):
        """Override copy to handle duplicated job orders"""
        default = dict(default or {})
        default.update({
            'name': f"{self.name} (Copy)",
            'progress': 0.0,
            'state': 'draft',
            'kanban_state': 'normal'
        })
        return super(JobOrder, self).copy(default)
    
    # Action methods for smart buttons
    def action_view_cost_sheets(self):
        """Action to view related cost sheets"""
        return {
            'name': 'Job Cost Sheets',
            'type': 'ir.actions.act_window',
            'res_model': 'job.cost.sheet',
            'view_mode': 'tree,form',
            'domain': [('job_order_id', '=', self.id)],
            'context': {'default_job_order_id': self.id, 'default_project_id': self.project_id.id}
        }
    
    def action_view_timesheets(self):
        """Action to view related timesheets"""
        return {
            'name': 'Timesheets',
            'type': 'ir.actions.act_window',
            'res_model': 'account.analytic.line',
            'view_mode': 'tree,form',
            'domain': [('job_order_id', '=', self.id)],
            'context': {'default_job_order_id': self.id, 'default_project_id': self.project_id.id}
        }
    
    def action_view_material_requisitions(self):
        """Action to view related material requisitions"""
        return {
            'name': 'Material Requisitions',
            'type': 'ir.actions.act_window',
            'res_model': 'material.requisition',
            'view_mode': 'tree,form',
            'domain': [('job_order_id', '=', self.id)],
            'context': {'default_job_order_id': self.id, 'default_project_id': self.project_id.id}
        }
    
    def action_view_notes(self):
        """Action to view related job notes"""
        return {
            'name': 'Job Notes',
            'type': 'ir.actions.act_window',
            'res_model': 'job.note',
            'view_mode': 'tree,form',
            'domain': [('job_order_id', '=', self.id)],
            'context': {'default_job_order_id': self.id}
        }
    
    def action_view_boqs(self):
        """Action to view related BOQs"""
        return {
            'name': 'Bill of Quantities',
            'type': 'ir.actions.act_window',
            'res_model': 'boq.boq',
            'view_mode': 'tree,form',
            'domain': [('job_order_id', '=', self.id)],
            'context': {'default_job_order_id': self.id, 'default_project_id': self.project_id.id}
        }
    
    def action_create_cost_sheet(self):
        """Action to create a new cost sheet for this job order"""
        cost_sheet_vals = {
            'name': f"Cost Sheet - {self.name}",
            'job_order_id': self.id,
            'project_id': self.project_id.id,
            'date_start': self.date_start or fields.Date.today(),
            'date_end': self.date_end,
        }
        
        # Set analytic account if project has one
        if self.project_id and self.project_id.analytic_account_id:
            cost_sheet_vals['analytic_account_id'] = self.project_id.analytic_account_id.id
        
        cost_sheet = self.env['job.cost.sheet'].create(cost_sheet_vals)
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Cost Sheet',
            'res_model': 'job.cost.sheet',
            'res_id': cost_sheet.id,
            'view_mode': 'form',
            'target': 'current',
        }
