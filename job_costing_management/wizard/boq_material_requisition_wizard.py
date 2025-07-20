# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class BOQMaterialRequisitionWizard(models.TransientModel):
    _name = 'boq.material.requisition.wizard'
    _description = 'BOQ Material Requisition Wizard'

    boq_id = fields.Many2one('boq.boq', string='BOQ', required=True)
    project_id = fields.Many2one('project.project', string='Project', related='boq_id.project_id', readonly=True)
    job_order_id = fields.Many2one('job.order', string='Job Order', related='boq_id.job_order_id', readonly=True)
    job_cost_sheet_id = fields.Many2one('job.cost.sheet', string='Job Cost Sheet', related='boq_id.job_cost_sheet_id', readonly=True)
    
    # Requisition details
    purpose = fields.Text(string='Purpose/Reason', required=True)
    required_date = fields.Date(string='Required Date', required=True, default=fields.Date.today)
    priority = fields.Selection([
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('urgent', 'Urgent')
    ], string='Priority', default='normal')
    
    # Lines
    line_ids = fields.One2many('boq.material.requisition.wizard.line', 'wizard_id', string='BOQ Lines')
    
    @api.model
    def default_get(self, fields_list):
        """Set default values including BOQ lines with remaining quantities"""
        res = super().default_get(fields_list)
        
        # Get BOQ from context
        boq_id = self.env.context.get('active_id')
        if boq_id and self.env.context.get('active_model') == 'boq.boq':
            boq = self.env['boq.boq'].browse(boq_id)
            res['boq_id'] = boq_id
            res['purpose'] = f'Material requisition from BOQ: {boq.name}'
            
            # Check if BOQ has any lines
            if not boq.line_ids:
                raise ValidationError(_('The selected BOQ has no lines. Please add BOQ lines before creating a material requisition.'))
            
            # Get BOQ lines with products and remaining quantities
            lines_with_products = boq.line_ids.filtered(lambda l: l.product_id)
            if not lines_with_products:
                raise ValidationError(_('The selected BOQ has no lines with products assigned. Please assign products to BOQ lines before creating a material requisition.'))
            
            lines_with_remaining = lines_with_products.filtered(lambda l: l.remaining_qty > 0)
            if not lines_with_remaining:
                raise ValidationError(_(
                    'All BOQ lines with products have been fully requisitioned. No remaining quantities available for requisition.\n\n'
                    'BOQ lines with products: %d\n'
                    'Lines fully requisitioned: %d'
                ) % (len(lines_with_products), len(lines_with_products)))
            
            line_vals = []
            for line in lines_with_remaining:
                # Ensure we have all required data
                if not line.product_id:
                    continue  # Skip lines without products
                
                line_vals.append((0, 0, {
                    'boq_line_id': line.id,
                    'product_id': line.product_id.id,
                    'description': line.description or line.product_id.name,
                    'boq_quantity': line.adjusted_quantity,
                    'requisitioned_quantity': line.total_requisitioned_qty,
                    'remaining_quantity': line.remaining_qty,
                    'requested_quantity': line.remaining_qty,  # Default to remaining quantity
                    'uom_id': line.uom_id.id if line.uom_id else line.product_id.uom_id.id,
                    'estimated_cost': line.unit_cost,
                    'selected': True,  # Select all by default
                }))
            
            if not line_vals:
                raise ValidationError(_('No valid BOQ lines found for requisition creation. Please ensure BOQ lines have products and remaining quantities.'))
            
            res['line_ids'] = line_vals
        
        return res
    
    def action_create_requisition(self):
        """Create material requisition from selected lines"""
        selected_lines = self.line_ids.filtered('selected')
        
        if not selected_lines:
            raise ValidationError(_('Please select at least one BOQ line to create requisition.'))
        
        # Check for lines with zero or negative quantities
        invalid_lines = selected_lines.filtered(lambda l: l.requested_quantity <= 0)
        if invalid_lines:
            raise ValidationError(_('Requested quantity must be greater than zero for all selected lines.'))
        
        # Validate selected lines have required data
        lines_missing_product = selected_lines.filtered(lambda l: not l.product_id)
        if lines_missing_product:
            raise ValidationError(_('The following lines are missing products and cannot be processed:\n%s') % 
                                '\n'.join([f'- {line.description}' for line in lines_missing_product]))
        
        lines_missing_uom = selected_lines.filtered(lambda l: not l.uom_id)
        if lines_missing_uom:
            raise ValidationError(_('The following lines are missing unit of measure and cannot be processed:\n%s') % 
                                '\n'.join([f'- {line.description}' for line in lines_missing_uom]))
        
        # Create material requisition
        requisition_vals = {
            'project_id': self.project_id.id,
            'job_order_id': self.job_order_id.id if self.job_order_id else False,
            'job_cost_sheet_id': self.job_cost_sheet_id.id if self.job_cost_sheet_id else False,
            'boq_id': self.boq_id.id,
            'purpose': self.purpose,
            'required_date': self.required_date,
            'priority': self.priority,
            'line_ids': []
        }
        
        for line in selected_lines:
            # Find the corresponding job cost line for this BOQ line
            job_cost_line = False
            if line.boq_line_id.cost_line_ids:
                job_cost_line = line.boq_line_id.cost_line_ids[0]
            
            req_line_vals = {
                'product_id': line.product_id.id,
                'description': line.description,
                'quantity': line.requested_quantity,
                'uom_id': line.uom_id.id,
                'estimated_cost': line.estimated_cost,
                'boq_line_id': line.boq_line_id.id,
                'job_cost_line_id': job_cost_line.id if job_cost_line else False,
            }
            requisition_vals['line_ids'].append((0, 0, req_line_vals))
        
        requisition = self.env['material.requisition'].create(requisition_vals)
        
        return {
            'name': _('Material Requisition'),
            'type': 'ir.actions.act_window',
            'res_model': 'material.requisition',
            'view_mode': 'form',
            'res_id': requisition.id,
            'target': 'current',
        }


class BOQMaterialRequisitionWizardLine(models.TransientModel):
    _name = 'boq.material.requisition.wizard.line'
    _description = 'BOQ Material Requisition Wizard Line'

    wizard_id = fields.Many2one('boq.material.requisition.wizard', string='Wizard', required=True, ondelete='cascade')
    selected = fields.Boolean(string='Select', default=True)
    
    # BOQ line information
    boq_line_id = fields.Many2one('boq.line', string='BOQ Line', required=True)
    product_id = fields.Many2one('product.product', string='Product', required=False)  # Changed to not required
    description = fields.Text(string='Description', required=True)
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure', required=False)  # Changed to not required
    estimated_cost = fields.Float(string='Estimated Unit Cost')
    
    # Quantity tracking
    boq_quantity = fields.Float(string='BOQ Quantity', readonly=True)
    requisitioned_quantity = fields.Float(string='Already Requisitioned', readonly=True)
    remaining_quantity = fields.Float(string='Remaining Quantity', readonly=True)
    requested_quantity = fields.Float(string='Requested Quantity', required=True)
    
    # Computed fields
    total_cost = fields.Float(string='Total Cost', compute='_compute_total_cost')
    quantity_status = fields.Selection([
        ('within', 'Within BOQ'),
        ('exceed', 'Exceeds BOQ'),
        ('complete', 'Fully Requisitioned')
    ], string='Status', compute='_compute_quantity_status')
    
    @api.depends('requested_quantity', 'estimated_cost')
    def _compute_total_cost(self):
        for record in self:
            record.total_cost = record.requested_quantity * record.estimated_cost
    
    @api.depends('requested_quantity', 'remaining_quantity')
    def _compute_quantity_status(self):
        for record in self:
            if record.remaining_quantity <= 0:
                record.quantity_status = 'complete'
            elif record.requested_quantity > record.remaining_quantity:
                record.quantity_status = 'exceed'
            else:
                record.quantity_status = 'within'
    
    @api.onchange('boq_line_id')
    def _onchange_boq_line_id(self):
        """Update fields when BOQ line changes"""
        if self.boq_line_id:
            self.product_id = self.boq_line_id.product_id
            self.description = self.boq_line_id.description or (self.boq_line_id.product_id.name if self.boq_line_id.product_id else '')
            self.uom_id = self.boq_line_id.uom_id or (self.boq_line_id.product_id.uom_id if self.boq_line_id.product_id else False)
            self.estimated_cost = self.boq_line_id.unit_cost
            self.boq_quantity = self.boq_line_id.adjusted_quantity
            self.requisitioned_quantity = self.boq_line_id.total_requisitioned_qty
            self.remaining_quantity = self.boq_line_id.remaining_qty
            self.requested_quantity = self.boq_line_id.remaining_qty
    
    @api.constrains('requested_quantity')
    def _check_requested_quantity(self):
        """Validate requested quantity"""
        for record in self:
            if record.requested_quantity < 0:
                raise ValidationError(_('Requested quantity cannot be negative for line: %s') % record.description)
    
    @api.constrains('product_id', 'selected')
    def _check_selected_line_data(self):
        """Ensure selected lines have required data"""
        for record in self:
            if record.selected:
                if not record.product_id:
                    raise ValidationError(_('Selected line "%s" must have a product assigned.') % record.description)
                if not record.uom_id:
                    raise ValidationError(_('Selected line "%s" must have a unit of measure.') % record.description)
    
    @api.onchange('requested_quantity')
    def _onchange_requested_quantity(self):
        """Show warning when requested quantity exceeds remaining quantity"""
        if self.requested_quantity and self.remaining_quantity:
            if self.requested_quantity > self.remaining_quantity:
                warning_msg = _(
                    'Warning: Requested quantity (%s %s) exceeds remaining BOQ quantity (%s %s).\n'
                    'You can still proceed if needed.'
                ) % (
                    self.requested_quantity, self.uom_id.name or '',
                    self.remaining_quantity, self.uom_id.name or ''
                )
                
                return {
                    'warning': {
                        'title': _('BOQ Quantity Exceeded'),
                        'message': warning_msg
                    }
                }