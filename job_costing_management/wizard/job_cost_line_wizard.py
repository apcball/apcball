# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class JobCostLineWizard(models.TransientModel):
    _name = 'job.cost.line.wizard'
    _description = 'Job Cost Line Wizard'

    job_cost_line_ids = fields.Many2many('job.cost.line', string='Job Cost Lines')
    new_cost_type = fields.Selection([
        ('material', 'Material'),
        ('labour', 'Labour'),
        ('overhead', 'Overhead')
    ], string='New Cost Type', required=True)
    clear_product = fields.Boolean(string='Clear Product Selection', default=True,
                                  help="Clear product selection when changing cost type to ensure proper domain filtering")

    @api.model
    def default_get(self, fields_list):
        """Set default values from context"""
        res = super().default_get(fields_list)
        active_ids = self.env.context.get('active_ids', [])
        if active_ids:
            res['job_cost_line_ids'] = [(6, 0, active_ids)]
        return res

    def action_update_cost_type(self):
        """Update cost type for selected job cost lines"""
        if not self.job_cost_line_ids:
            raise ValidationError(_("Please select at least one job cost line to update."))
        
        # Update cost type for all selected lines
        for line in self.job_cost_line_ids:
            vals = {'cost_type': self.new_cost_type}
            
            # Clear product if requested or if it doesn't match the new cost type
            if self.clear_product or not self._is_product_compatible(line.product_id, self.new_cost_type):
                vals['product_id'] = False
            
            # Set appropriate UOM based on cost type
            if self.new_cost_type == 'labour':
                hours_uom = self.env['uom.uom'].search([('name', 'ilike', 'hour')], limit=1)
                if hours_uom:
                    vals['uom_id'] = hours_uom.id
            elif self.new_cost_type == 'material':
                units_uom = self.env['uom.uom'].search([('name', 'ilike', 'unit')], limit=1)
                if units_uom:
                    vals['uom_id'] = units_uom.id
            
            line.write(vals)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Cost type updated for %d job cost line(s).') % len(self.job_cost_line_ids),
                'type': 'success',
            }
        }

    def _is_product_compatible(self, product, cost_type):
        """Check if product is compatible with cost type"""
        if not product:
            return True
        
        if cost_type == 'material' and product.detailed_type == 'service':
            return False
        elif cost_type == 'labour' and product.detailed_type != 'service':
            return False
        
        return True


class JobCostLineBulkEditWizard(models.TransientModel):
    _name = 'job.cost.line.bulk.edit.wizard'
    _description = 'Job Cost Line Bulk Edit Wizard'

    job_cost_line_ids = fields.Many2many('job.cost.line', string='Job Cost Lines')
    
    # Fields to update
    update_cost_type = fields.Boolean(string='Update Cost Type')
    new_cost_type = fields.Selection([
        ('material', 'Material'),
        ('labour', 'Labour'),
        ('overhead', 'Overhead')
    ], string='New Cost Type')
    
    update_unit_cost = fields.Boolean(string='Update Unit Cost')
    new_unit_cost = fields.Float(string='New Unit Cost')
    
    update_planned_qty = fields.Boolean(string='Update Planned Quantity')
    new_planned_qty = fields.Float(string='New Planned Quantity')
    
    update_analytic_account = fields.Boolean(string='Update Analytic Account')
    new_analytic_account_id = fields.Many2one('account.analytic.account', string='New Analytic Account')

    @api.model
    def default_get(self, fields_list):
        """Set default values from context"""
        res = super().default_get(fields_list)
        active_ids = self.env.context.get('active_ids', [])
        if active_ids:
            res['job_cost_line_ids'] = [(6, 0, active_ids)]
        return res

    def action_bulk_update(self):
        """Perform bulk update on selected job cost lines"""
        if not self.job_cost_line_ids:
            raise ValidationError(_("Please select at least one job cost line to update."))
        
        vals = {}
        
        if self.update_cost_type and self.new_cost_type:
            vals['cost_type'] = self.new_cost_type
        
        if self.update_unit_cost:
            vals['unit_cost'] = self.new_unit_cost
        
        if self.update_planned_qty:
            vals['planned_qty'] = self.new_planned_qty
        
        if self.update_analytic_account:
            vals['analytic_account_id'] = self.new_analytic_account_id.id if self.new_analytic_account_id else False
        
        if not vals:
            raise ValidationError(_("Please select at least one field to update."))
        
        # Update all selected lines
        self.job_cost_line_ids.write(vals)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Bulk update completed for %d job cost line(s).') % len(self.job_cost_line_ids),
                'type': 'success',
            }
        }