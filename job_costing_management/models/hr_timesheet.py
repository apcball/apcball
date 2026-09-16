# -*- coding: utf-8 -*-

from odoo import models, fields, api


class AccountAnalyticLine(models.Model):
    _inherit = 'account.analytic.line'

    job_cost_line_id = fields.Many2one('job.cost.line', string='Job Cost Line', index=True)
    job_order_id = fields.Many2one('job.order', string='Job Order', index=True)
    project_id = fields.Many2one('project.project', string='Project', related='task_id.project_id', store=True, index=True)
    
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
        import logging
        _logger = logging.getLogger(__name__)
        
        if not self.account_id:
            return
            
        # Find related job cost sheet
        cost_sheet = self.env['job.cost.sheet'].search([
            ('analytic_account_id', '=', self.account_id.id),
            ('state', 'in', ['approved', 'done'])
        ], limit=1)
        
        if cost_sheet:
            # FIX ISSUE #2: Check if there's already a cost line linked to this timesheet
            existing_cost_line = self.env['job.cost.line'].sudo().search([
                ('source_timesheet_id', '=', self.id)
            ], limit=1)
            
            if existing_cost_line:
                _logger.info(f"Timesheet {self.name} already linked to cost line {existing_cost_line.id}")
                self.job_cost_line_id = existing_cost_line.id
                return
            
            # Find matching labour cost line
            labour_lines = cost_sheet.labour_cost_ids
            
            if len(labour_lines) == 1:
                # If only one labour line, auto-link
                self.job_cost_line_id = labour_lines[0].id
                
                # Debug logging
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
    
    def _get_display_amount(self):
        """
        FIX ISSUE #1: Return positive amount for display purposes.
        Timesheet amounts are stored as negative in Odoo (costs),
        but for display and reporting we want positive values.
        """
        self.ensure_one()
        return abs(self.amount) if self.amount else 0.0
    
    def action_create_job_cost_line(self):
        """
        Create a job cost line from this timesheet if one doesn't exist.
        FIX ISSUE #2: Prevents duplicate cost lines.
        """
        self.ensure_one()
        import logging
        _logger = logging.getLogger(__name__)
        
        # Check if already linked
        if self.job_cost_line_id:
            _logger.info(f"Timesheet {self.name} already linked to cost line {self.job_cost_line_id.id}")
            return self.job_cost_line_id
        
        # Check for existing cost line with this timesheet as source
        existing = self.env['job.cost.line'].sudo().search([
            ('source_timesheet_id', '=', self.id)
        ], limit=1)
        
        if existing:
            _logger.info(f"Found existing cost line for timesheet {self.id}: {existing.id}")
            self.job_cost_line_id = existing.id
            return existing
        
        # Find job cost sheet
        cost_sheet = self.env['job.cost.sheet'].search([
            ('analytic_account_id', '=', self.account_id.id),
            ('state', 'in', ['approved', 'done'])
        ], limit=1)
        
        if not cost_sheet:
            _logger.warning(f"No job cost sheet found for timesheet {self.name}")
            return False
        
        # Create new labour cost line
        cost_line_vals = {
            'cost_sheet_id': cost_sheet.id,
            'cost_type': 'labour',
            'name': self.name or _('Labour - %s') % self.employee_id.name,
            'planned_qty': 0,  # No planned qty for auto-created lines
            'actual_qty': self.unit_amount,
            'unit_cost': abs(self.amount) / self.unit_amount if self.unit_amount else 0,
            'uom_id': self.env.ref('uom.product_uom_hour').id if self.env.ref('uom.product_uom_hour', False) else False,
            'analytic_account_id': self.account_id.id,
            'source_timesheet_id': self.id,  # Track source to prevent duplicates
        }
        
        new_line = self.env['job.cost.line'].sudo().create(cost_line_vals)
        self.job_cost_line_id = new_line.id
        
        _logger.info(f"Created new labour cost line {new_line.id} for timesheet {self.name}")
        return new_line


class HrEmployee(models.Model):
    _inherit = 'hr.employee'
    
    dest_location_id = fields.Many2one('stock.location', string='Destination Location',
                                      help='Default destination location for material requisitions')


class HrDepartment(models.Model):
    _inherit = 'hr.department'
    
    dest_location_id = fields.Many2one('stock.location', string='Destination Location',
                                      help='Default destination location for material requisitions')
