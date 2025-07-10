# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ProjectProject(models.Model):
    _inherit = 'project.project'

    # Job costing fields
    job_type_id = fields.Many2one('job.type', string='Job Type')
    is_job_project = fields.Boolean(string='Is Job Project', default=False)
    contract_amount = fields.Float(string='Contract Amount')
    contract_date = fields.Date(string='Contract Date')
    client_id = fields.Many2one('res.partner', string='Client')
    project_manager_id = fields.Many2one('res.users', string='Project Manager')
    
    # Cost sheet relation
    job_cost_sheet_ids = fields.One2many('job.cost.sheet', 'project_id', string='Job Cost Sheets')
    job_cost_sheet_count = fields.Integer(string='Cost Sheets', compute='_compute_job_cost_sheet_count')
    
    # Job orders (tasks)
    job_order_ids = fields.One2many('job.order', 'project_id', string='Job Orders')
    job_order_count = fields.Integer(string='Job Orders', compute='_compute_job_order_count')
    
    # Material requisitions
    material_requisition_ids = fields.One2many('material.requisition', 'project_id', string='Material Requisitions')
    material_requisition_count = fields.Integer(string='Material Requisitions', compute='_compute_material_requisition_count')
    
    # BOQ
    boq_ids = fields.One2many('boq.boq', 'project_id', string='BOQ')
    boq_count = fields.Integer(string='BOQ', compute='_compute_boq_count')
    
    # Subcontractors
    subcontractor_ids = fields.Many2many('res.partner', 'project_subcontractor_rel', 
                                        'project_id', 'partner_id', 
                                        string='Subcontractors',
                                        domain=[('is_subcontractor', '=', True)])
    
    # Project notes
    project_note_ids = fields.One2many('job.note', 'project_id', string='Project Notes')
    project_note_count = fields.Integer(string='Project Notes', compute='_compute_project_note_count')
    
    # Cost totals
    total_planned_cost = fields.Float(string='Total Planned Cost', compute='_compute_cost_totals', store=True)
    total_actual_cost = fields.Float(string='Total Actual Cost', compute='_compute_cost_totals', store=True)
    cost_variance = fields.Float(string='Cost Variance', compute='_compute_cost_totals', store=True)
    
    # Progress
    cost_progress = fields.Float(string='Cost Progress %', compute='_compute_cost_progress')
    
    @api.depends('job_cost_sheet_ids')
    def _compute_job_cost_sheet_count(self):
        for record in self:
            record.job_cost_sheet_count = len(record.job_cost_sheet_ids)
    
    @api.depends('job_order_ids')
    def _compute_job_order_count(self):
        for record in self:
            record.job_order_count = len(record.job_order_ids)
    
    @api.depends('material_requisition_ids')
    def _compute_material_requisition_count(self):
        for record in self:
            record.material_requisition_count = len(record.material_requisition_ids)
    
    @api.depends('boq_ids')
    def _compute_boq_count(self):
        for record in self:
            record.boq_count = len(record.boq_ids)
    
    @api.depends('project_note_ids')
    def _compute_project_note_count(self):
        for record in self:
            record.project_note_count = len(record.project_note_ids)
    
    @api.depends('job_cost_sheet_ids.total_cost', 'job_cost_sheet_ids.actual_total_cost')
    def _compute_cost_totals(self):
        for record in self:
            record.total_planned_cost = sum(record.job_cost_sheet_ids.mapped('total_cost'))
            record.total_actual_cost = sum(record.job_cost_sheet_ids.mapped('actual_total_cost'))
            record.cost_variance = record.total_actual_cost - record.total_planned_cost
    
    @api.depends('total_planned_cost', 'total_actual_cost')
    def _compute_cost_progress(self):
        for record in self:
            if record.total_planned_cost:
                record.cost_progress = (record.total_actual_cost / record.total_planned_cost) * 100
            else:
                record.cost_progress = 0
    
    def action_view_job_cost_sheets(self):
        return {
            'name': 'Job Cost Sheets',
            'type': 'ir.actions.act_window',
            'res_model': 'job.cost.sheet',
            'view_mode': 'tree,form',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id}
        }
    
    def action_view_job_orders(self):
        return {
            'name': 'Job Orders',
            'type': 'ir.actions.act_window',
            'res_model': 'job.order',
            'view_mode': 'tree,form,kanban',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id}
        }
    
    def action_view_material_requisitions(self):
        return {
            'name': 'Material Requisitions',
            'type': 'ir.actions.act_window',
            'res_model': 'material.requisition',
            'view_mode': 'tree,form',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id}
        }
    
    def action_view_boq(self):
        return {
            'name': 'BOQ',
            'type': 'ir.actions.act_window',
            'res_model': 'boq.boq',
            'view_mode': 'tree,form',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id}
        }
    
    def action_create_job_cost_sheet(self):
        return {
            'name': 'Create Job Cost Sheet',
            'type': 'ir.actions.act_window',
            'res_model': 'job.cost.sheet',
            'view_mode': 'form',
            'context': {
                'default_project_id': self.id,
                'default_analytic_account_id': self.analytic_account_id.id if self.analytic_account_id else False
            },
            'target': 'new'
        }
    
    def action_create_boq(self):
        return {
            'name': 'Create BOQ',
            'type': 'ir.actions.act_window',
            'res_model': 'boq.boq',
            'view_mode': 'form',
            'context': {
                'default_project_id': self.id,
                'default_title': f'BOQ for {self.name}',
            },
            'target': 'new'
        }
