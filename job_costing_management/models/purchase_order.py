# -*- coding: utf-8 -*-

from odoo import models, fields, api


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    material_requisition_id = fields.Many2one('material.requisition', string='Material Requisition')
    job_cost_sheet_id = fields.Many2one('job.cost.sheet', string='Job Cost Sheet')
    project_id = fields.Many2one('project.project', string='Project')
    job_order_id = fields.Many2one('job.order', string='Job Order')


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    material_requisition_line_id = fields.Many2one('material.requisition.line', string='Requisition Line')
    job_cost_line_id = fields.Many2one('job.cost.line', string='Job Cost Line')
    analytic_account_id = fields.Many2one('account.analytic.account', string='Analytic Account')
    
    @api.model
    def create(self, vals):
        result = super(PurchaseOrderLine, self).create(vals)
        
        # Auto-link to job cost sheet if analytic account is provided
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
