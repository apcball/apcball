# -*- coding: utf-8 -*-

from odoo import models, fields, api


class AccountAnalyticLine(models.Model):
    _inherit = 'account.analytic.line'

    job_cost_line_id = fields.Many2one('job.cost.line', string='Job Cost Line')
    job_order_id = fields.Many2one('job.order', string='Job Order')
    project_id = fields.Many2one('project.project', string='Project', related='task_id.project_id', store=True)
    
    @api.onchange('job_order_id')
    def _onchange_job_order_id(self):
        """When job order changes, update project"""
        if self.job_order_id and self.job_order_id.project_id:
            self.project_id = self.job_order_id.project_id.id
    
    @api.onchange('account_id')
    def _onchange_account_id(self):
        if self.account_id:
            # Find related job cost sheet
            cost_sheet = self.env['job.cost.sheet'].search([
                ('analytic_account_id', '=', self.account_id.id),
                ('state', '=', 'approved')
            ], limit=1)
            
            if cost_sheet:
                domain = [('cost_sheet_id', '=', cost_sheet.id), ('cost_type', '=', 'labour')]
                return {'domain': {'job_cost_line_id': domain}}
    
    @api.onchange('task_id')
    def _onchange_task_id(self):
        if self.task_id:
            # Find related job order
            job_order = self.env['job.order'].search([
                ('task_id', '=', self.task_id.id)
            ], limit=1)
            
            if job_order:
                self.job_order_id = job_order.id


class HrEmployee(models.Model):
    _inherit = 'hr.employee'
    
    dest_location_id = fields.Many2one('stock.location', string='Destination Location',
                                      help='Default destination location for material requisitions')


class HrDepartment(models.Model):
    _inherit = 'hr.department'
    
    dest_location_id = fields.Many2one('stock.location', string='Destination Location',
                                      help='Default destination location for material requisitions')
