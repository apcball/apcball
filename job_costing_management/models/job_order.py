# -*- coding: utf-8 -*-

from odoo import models, fields, api


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
    
    # Costs
    job_cost_sheet_ids = fields.One2many('job.cost.sheet', 'job_order_id', string='Job Cost Sheets')
    planned_cost = fields.Float(string='Planned Cost', compute='_compute_costs', store=True)
    actual_cost = fields.Float(string='Actual Cost', compute='_compute_costs', store=True)
    
    # Material management
    material_planning_ids = fields.One2many('material.planning', 'job_order_id', string='Material Planning')
    material_consumption_ids = fields.One2many('material.consumption', 'job_order_id', string='Material Consumption')
    material_requisition_ids = fields.One2many('material.requisition', 'job_order_id', string='Material Requisitions')
    
    # Timesheets
    timesheet_ids = fields.One2many('account.analytic.line', 'job_order_id', string='Timesheets')
    
    # Notes
    job_note_ids = fields.One2many('job.note', 'job_order_id', string='Job Notes')
    
    # Smart button counts
    cost_sheet_count = fields.Integer(string='Cost Sheets', compute='_compute_counts')
    timesheet_count = fields.Integer(string='Timesheets', compute='_compute_counts')
    material_requisition_count = fields.Integer(string='Material Requisitions', compute='_compute_counts')
    note_count = fields.Integer(string='Notes', compute='_compute_counts')
    
    # Other fields
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    active = fields.Boolean(string='Active', default=True)
    color = fields.Integer(string='Color Index')
    
    @api.depends('job_cost_sheet_ids.total_cost', 'job_cost_sheet_ids.actual_total_cost')
    def _compute_costs(self):
        for record in self:
            record.planned_cost = sum(record.job_cost_sheet_ids.mapped('total_cost'))
            record.actual_cost = sum(record.job_cost_sheet_ids.mapped('actual_total_cost'))
    
    @api.depends('job_cost_sheet_ids', 'timesheet_ids', 'material_requisition_ids', 'job_note_ids')
    def _compute_counts(self):
        for record in self:
            record.cost_sheet_count = len(record.job_cost_sheet_ids)
            record.timesheet_count = len(record.timesheet_ids)
            record.material_requisition_count = len(record.material_requisition_ids)
            record.note_count = len(record.job_note_ids)
    
    def action_view_cost_sheets(self):
        return {
            'name': 'Job Cost Sheets',
            'type': 'ir.actions.act_window',
            'res_model': 'job.cost.sheet',
            'view_mode': 'tree,form',
            'domain': [('job_order_id', '=', self.id)],
            'context': {'default_job_order_id': self.id, 'default_project_id': self.project_id.id}
        }
    
    def action_view_timesheets(self):
        return {
            'name': 'Timesheets',
            'type': 'ir.actions.act_window',
            'res_model': 'account.analytic.line',
            'view_mode': 'tree,form',
            'domain': [('job_order_id', '=', self.id)],
            'context': {'default_job_order_id': self.id}
        }
    
    def action_view_material_requisitions(self):
        return {
            'name': 'Material Requisitions',
            'type': 'ir.actions.act_window',
            'res_model': 'material.requisition',
            'view_mode': 'tree,form',
            'domain': [('job_order_id', '=', self.id)],
            'context': {'default_job_order_id': self.id, 'default_project_id': self.project_id.id}
        }
    
    def action_view_notes(self):
        return {
            'name': 'Job Notes',
            'type': 'ir.actions.act_window',
            'res_model': 'job.note',
            'view_mode': 'tree,form',
            'domain': [('job_order_id', '=', self.id)],
            'context': {'default_job_order_id': self.id, 'default_project_id': self.project_id.id}
        }


class MaterialPlanning(models.Model):
    _name = 'material.planning'
    _description = 'Material Planning'

    job_order_id = fields.Many2one('job.order', string='Job Order', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product', required=True)
    description = fields.Char(string='Description')
    planned_qty = fields.Float(string='Planned Quantity', default=1.0)
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure')
    planned_date = fields.Date(string='Planned Date', default=fields.Date.today)
    notes = fields.Text(string='Notes')
    
    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.description = self.product_id.name
            self.uom_id = self.product_id.uom_id


class MaterialConsumption(models.Model):
    _name = 'material.consumption'
    _description = 'Material Consumption'

    job_order_id = fields.Many2one('job.order', string='Job Order', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product', required=True)
    description = fields.Char(string='Description')
    consumed_qty = fields.Float(string='Consumed Quantity', default=1.0)
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure')
    consumption_date = fields.Date(string='Consumption Date', default=fields.Date.today)
    location_id = fields.Many2one('stock.location', string='Location')
    notes = fields.Text(string='Notes')
    
    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.description = self.product_id.name
            self.uom_id = self.product_id.uom_id
