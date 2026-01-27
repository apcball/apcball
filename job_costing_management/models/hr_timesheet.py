# -*- coding: utf-8 -*-

from odoo import models, fields, api


class AccountAnalyticLine(models.Model):
    _inherit = 'account.analytic.line'

    job_cost_line_id = fields.Many2one('job.cost.line', string='Job Cost Line')
    job_order_id = fields.Many2one('job.order', string='Job Order')
    project_id = fields.Many2one('project.project', string='Project', related='task_id.project_id', store=True)
    
    @api.model
    def create(self, vals):
        result = super(AccountAnalyticLine, self).create(vals)
        
        # Auto-link to job cost line if not already linked
        if not result.job_cost_line_id and result.account_id:
            result._auto_link_to_job_cost_line()
            
        return result
    
    def write(self, vals):
        result = super(AccountAnalyticLine, self).write(vals)
        
        # If analytic account changed, try to auto-link
        if 'account_id' in vals:
            for record in self:
                if not record.job_cost_line_id:
                    record._auto_link_to_job_cost_line()
                    
        return result
    
    def _auto_link_to_job_cost_line(self):
        """Auto-link timesheet to appropriate job cost line"""
        if not self.account_id:
            return
            
        # Find related job cost sheet
        cost_sheet = self.env['job.cost.sheet'].search([
            ('analytic_account_id', '=', self.account_id.id),
            ('state', 'in', ['approved', 'done'])
        ], limit=1)
        
        if cost_sheet:
            # Find matching labour cost line
            labour_lines = cost_sheet.labour_cost_ids
            
            if len(labour_lines) == 1:
                # If only one labour line, auto-link
                self.job_cost_line_id = labour_lines[0].id
                
                # Debug logging
                import logging
                _logger = logging.getLogger(__name__)
                _logger.info(f"Auto-linked timesheet {self.name} to job cost line {labour_lines[0].name}")
                
            elif len(labour_lines) > 1 and self.task_id:
                # Try to match by task/job order
                job_order = self.env['job.order'].search([
                    ('task_id', '=', self.task_id.id)
                ], limit=1)
                
                if job_order:
                    # Find labour line for this job order
                    matching_line = labour_lines.filtered(
                        lambda l: l.name and job_order.name in l.name
                    )
                    if matching_line:
                        self.job_cost_line_id = matching_line[0].id
    
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
                ('state', 'in', ['approved', 'done'])
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
