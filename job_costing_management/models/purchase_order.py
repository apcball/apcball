# -*- coding: utf-8 -*-

from odoo import models, fields, api


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    material_requisition_id = fields.Many2one('material.requisition', string='Material Requisition')
    job_cost_sheet_id = fields.Many2one('job.cost.sheet', string='Job Cost Sheet')
    project_id = fields.Many2one('project.project', string='Project')
    job_order_id = fields.Many2one('job.order', string='Job Order')
    
    @api.model
    def create(self, vals):
        result = super(PurchaseOrder, self).create(vals)
        
        # Debug logging
        import logging
        _logger = logging.getLogger(__name__)
        _logger.info(f"Creating purchase order: {result.name}")
        
        # Auto-link to job cost sheet if material requisition is provided
        if result.material_requisition_id and result.material_requisition_id.boq_id:
            _logger.info(f"Purchase order has material requisition: {result.material_requisition_id.name}")
            boq = result.material_requisition_id.boq_id
            _logger.info(f"Material requisition linked to BOQ: {boq.name}")
            
            if boq.job_cost_sheet_id:
                _logger.info(f"BOQ linked to job cost sheet: {boq.job_cost_sheet_id.name}")
                result.job_cost_sheet_id = boq.job_cost_sheet_id.id
                result.project_id = boq.project_id.id
                result.job_order_id = boq.job_order_id.id if boq.job_order_id else False
                
                # Also set analytic account if available
                if boq.job_cost_sheet_id.analytic_account_id:
                    _logger.info(f"Setting analytic account on PO lines: {boq.job_cost_sheet_id.analytic_account_id.name}")
                    # Set analytic account on purchase order lines
                    for line in result.order_line:
                        line.analytic_account_id = boq.job_cost_sheet_id.analytic_account_id.id
                
                _logger.info(f"Purchase order successfully linked to job cost sheet: {result.job_cost_sheet_id.name}")
            else:
                _logger.warning(f"BOQ {boq.name} has no job cost sheet linked")
        else:
            _logger.info("Purchase order has no material requisition or BOQ")
        
        return result


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    material_requisition_line_id = fields.Many2one('material.requisition.line', string='Requisition Line')
    job_cost_line_id = fields.Many2one('job.cost.line', string='Job Cost Line')
    analytic_account_id = fields.Many2one('account.analytic.account', string='Analytic Account')
    
    @api.model
    def create(self, vals):
        result = super(PurchaseOrderLine, self).create(vals)
        
        # Debug logging
        import logging
        _logger = logging.getLogger(__name__)
        
        # Link to job cost line from material requisition line
        if result.material_requisition_line_id:
            req_line = result.material_requisition_line_id
            _logger.info(f"Processing PO line with requisition line: {req_line.id}")
            
            # First try to link through BOQ line
            if req_line.boq_line_id:
                boq_line = req_line.boq_line_id
                _logger.info(f"Found BOQ line: {boq_line.id}")
                # Find matching job cost line
                if boq_line.cost_line_ids:
                    matching_cost_line = boq_line.cost_line_ids.filtered(
                        lambda l: l.product_id == result.product_id
                    )
                    if matching_cost_line:
                        result.job_cost_line_id = matching_cost_line[0].id
                        _logger.info(f"Linked to job cost line: {matching_cost_line[0].id}")
                        # Also set analytic account if available
                        if matching_cost_line[0].analytic_account_id:
                            result.analytic_account_id = matching_cost_line[0].analytic_account_id.id
            
            # If no job cost line found from BOQ, try material requisition project
            if not result.job_cost_line_id and req_line.requisition_id.project_id:
                project = req_line.requisition_id.project_id
                _logger.info(f"Trying to find job cost sheet for project: {project.name}")
                # Find job cost sheet for this project
                cost_sheet = self.env['job.cost.sheet'].search([
                    ('project_id', '=', project.id),
                    ('state', '=', 'approved')
                ], limit=1)
                
                if cost_sheet:
                    # Set analytic account
                    if cost_sheet.analytic_account_id:
                        result.analytic_account_id = cost_sheet.analytic_account_id.id
                    
                    # Check if there's an existing cost line for this product
                    existing_line = cost_sheet.material_cost_ids.filtered(
                        lambda l: l.product_id == result.product_id
                    )
                    
                    if existing_line:
                        result.job_cost_line_id = existing_line[0].id
                    else:
                        # Create new cost line
                        cost_line_vals = {
                            'cost_sheet_id': cost_sheet.id,
                            'cost_type': 'material',
                            'product_id': result.product_id.id,
                            'name': result.product_id.name,
                            'planned_qty': result.product_qty,
                            'unit_cost': result.price_unit,
                            'uom_id': result.product_uom.id,
                            'analytic_account_id': cost_sheet.analytic_account_id.id if cost_sheet.analytic_account_id else False,
                        }
                        new_cost_line = self.env['job.cost.line'].create(cost_line_vals)
                        result.job_cost_line_id = new_cost_line.id
        
        # Auto-link to job cost sheet if analytic account is provided (fallback)
        if result.analytic_account_id and not result.job_cost_line_id:
            # Find matching job cost sheet
            cost_sheet = self.env['job.cost.sheet'].search([
                ('analytic_account_id', '=', result.analytic_account_id.id),
                ('state', '=', 'approved')
            ], limit=1)
            
            if cost_sheet:
                # Check if there's an existing cost line for this product
                existing_line = cost_sheet.material_cost_ids.filtered(
                    lambda l: l.product_id == result.product_id
                )
                
                if existing_line:
                    result.job_cost_line_id = existing_line[0].id
                else:
                    # Create new cost line
                    cost_line_vals = {
                        'cost_sheet_id': cost_sheet.id,
                        'cost_type': 'material',
                        'product_id': result.product_id.id,
                        'name': result.product_id.name,
                        'planned_qty': result.product_qty,
                        'unit_cost': result.price_unit,
                        'uom_id': result.product_uom.id,
                        'analytic_account_id': result.analytic_account_id.id,
                    }
                    new_cost_line = self.env['job.cost.line'].create(cost_line_vals)
                    result.job_cost_line_id = new_cost_line.id
        
        return result
    
    @api.onchange('analytic_account_id')
    def _onchange_analytic_account_id(self):
        if self.analytic_account_id:
            # Find related job cost sheet
            cost_sheet = self.env['job.cost.sheet'].search([
                ('analytic_account_id', '=', self.analytic_account_id.id),
                ('state', '=', 'approved')
            ], limit=1)
            
            if cost_sheet:
                domain = [('cost_sheet_id', '=', cost_sheet.id), ('cost_type', 'in', ['material', 'overhead'])]
                return {'domain': {'job_cost_line_id': domain}}
