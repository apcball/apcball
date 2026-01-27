# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class CreateRfqFromJobCost(models.TransientModel):
    _name = 'create.rfq.from.job.cost'
    _description = 'Create RFQ from Job Cost Sheet'

    job_cost_sheet_id = fields.Many2one('job.cost.sheet', string='Job Cost Sheet', required=True)
    partner_id = fields.Many2one('res.partner', string='Vendor', required=True, 
                                domain=[('is_company', '=', True), ('supplier_rank', '>', 0)])
    cost_line_ids = fields.Many2many('job.cost.line', string='Cost Lines to Include',
                                   domain="[('cost_sheet_id', '=', job_cost_sheet_id), ('cost_type', 'in', ['material', 'overhead', 'labour'])]")
    
    @api.onchange('job_cost_sheet_id')
    def _onchange_job_cost_sheet_id(self):
        if self.job_cost_sheet_id:
            # Auto-select all material, overhead, and labour cost lines that can be purchased
            cost_lines = (self.job_cost_sheet_id.material_cost_ids + 
                         self.job_cost_sheet_id.overhead_cost_ids + 
                         self.job_cost_sheet_id.labour_cost_ids.filtered(lambda l: l.product_id.purchase_ok))
            self.cost_line_ids = [(6, 0, cost_lines.ids)]
    
    def action_create_rfq(self):
        """Create RFQ with selected cost lines"""
        if not self.cost_line_ids:
            raise UserError(_('Please select at least one cost line to include in the RFQ.'))
        
        # Create purchase order
        po_vals = {
            'partner_id': self.partner_id.id,
            'job_cost_sheet_id': self.job_cost_sheet_id.id,
            'project_id': self.job_cost_sheet_id.project_id.id,
            'origin': f'Job Cost Sheet: {self.job_cost_sheet_id.name}',
            'order_line': []
        }
        
        # Create order lines from selected cost lines
        for cost_line in self.cost_line_ids:
            if cost_line.product_id:
                line_vals = {
                    'product_id': cost_line.product_id.id,
                    'name': cost_line.name,
                    'product_qty': cost_line.planned_qty,
                    'product_uom': cost_line.uom_id.id or cost_line.product_id.uom_po_id.id,
                    'price_unit': cost_line.unit_cost,
                    'job_cost_sheet_id': self.job_cost_sheet_id.id,
                    'job_cost_line_id': cost_line.id,
                    'analytic_account_id': cost_line.analytic_account_id.id if cost_line.analytic_account_id else False,
                }
                po_vals['order_line'].append((0, 0, line_vals))
        
        if not po_vals['order_line']:
            raise UserError(_('No valid products found in the selected cost lines. Please ensure cost lines have products assigned.'))
        
        # Create the purchase order with context to allow flexible product validation
        purchase_order = self.env['purchase.order'].with_context(
            skip_product_validation=True,
            flexible_product_validation=True
        ).create(po_vals)
        
        # Return action to open the created RFQ
        return {
            'type': 'ir.actions.act_window',
            'name': 'Request for Quotation',
            'res_model': 'purchase.order',
            'res_id': purchase_order.id,
            'view_mode': 'form',
            'target': 'current',
            'context': {'create': False}
        }
