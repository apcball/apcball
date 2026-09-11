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
    
    display_in_wizard = fields.Boolean(string='Display in Wizard', default=True)
    
    # Wizard State
    wizard_state = fields.Selection([
        ('select', 'Select Materials'),
        ('configure', 'Configure Quantities')
    ], string='Wizard State', default='select', required=True)
    
    # Step 1: Selection
    boq_line_selection_ids = fields.Many2many('boq.line', string='Select BOQ Lines',
                                             domain="[('boq_id', '=', boq_id), ('remaining_qty', '>', 0)]")
    
    # Step 2: Configuration
    line_ids = fields.One2many('boq.material.requisition.wizard.line', 'wizard_id', string='Requisition Lines')
    
    # Summary Statistics
    total_lines_count = fields.Integer(string='Total Lines', compute='_compute_statistics', readonly=True)
    selected_total_quantity = fields.Float(string='Total Requested Quantity', compute='_compute_statistics', readonly=True)
    selected_total_cost = fields.Float(string='Total Estimated Cost', compute='_compute_statistics', readonly=True, 
                                       currency_field='currency_id')
    
    # Currency for cost display
    currency_id = fields.Many2one('res.currency', string='Currency', 
                                 default=lambda self: self.env.company.currency_id)
    
    @api.depends('line_ids')
    def _compute_statistics(self):
        for record in self:
            record.total_lines_count = len(record.line_ids)
            record.selected_total_quantity = sum(record.line_ids.mapped('requested_quantity'))
            record.selected_total_cost = sum(record.line_ids.mapped('total_cost'))
    
    @api.model
    def default_get(self, fields_list):
        """Set default values"""
        res = super().default_get(fields_list)
        
        # Get BOQ from context
        boq_id = self.env.context.get('active_id')
        if boq_id and self.env.context.get('active_model') == 'boq.boq':
            boq = self.env['boq.boq'].browse(boq_id)
            res['boq_id'] = boq_id
            res['purpose'] = f'Material requisition from BOQ: {boq.name}'
            
            # Check availability
            if not boq.line_ids:
                raise ValidationError(_('The selected BOQ has no lines.'))
                
        return res
    
    def action_process_selection(self):
        """Process selected lines and move to configuration step"""
        self.ensure_one()
        
        if not self.boq_line_selection_ids:
            raise ValidationError(_('Please select at least one material to requisition.'))
            
        # Prepare lines for configuration step
        line_vals = []
        for line in self.boq_line_selection_ids:
            # Check if line is already in line_ids to preserve any edits if user goes back and comes forward
            existing_line = self.line_ids.filtered(lambda l: l.boq_line_id.id == line.id)
            if existing_line:
                continue
                
            line_vals.append((0, 0, {
                'boq_line_id': line.id,
                'product_id': line.product_id.id,
                'description': line.description or line.product_id.name,
                'boq_quantity': line.adjusted_quantity,
                'requisitioned_quantity': line.total_requisitioned_qty,
                'remaining_quantity': line.remaining_qty,
                'requested_quantity': line.remaining_qty,
                'uom_id': line.uom_id.id,
                'estimated_cost': line.unit_cost,
                'category_id': line.category_id.id if line.category_id else False,
                'product_category_id': line.product_id.categ_id.id if line.product_id.categ_id else False,
            }))
            
        if line_vals:
            self.write({'line_ids': line_vals})
            
        self.wizard_state = 'configure'
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }
    
    def action_go_back_to_selection(self):
        """Go back to selection state"""
        self.ensure_one()
        self.wizard_state = 'select'
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }
    
    def action_create_requisition(self):
        """Create material requisition from configured lines"""
        self.ensure_one()
        # All lines in the configuration step are considered selected
        selected_lines = self.line_ids
        
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
    _order = 'sequence, id'

    wizard_id = fields.Many2one('boq.material.requisition.wizard', string='Wizard', required=True, ondelete='cascade')
    
    # Sequence for ordering
    sequence = fields.Integer(string='Sequence', default=10)
    
    # BOQ line information
    boq_line_id = fields.Many2one('boq.line', string='BOQ Line', required=True)
    product_id = fields.Many2one('product.product', string='Product', required=False)
    description = fields.Text(string='Description', required=True)
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure', required=False)
    estimated_cost = fields.Float(string='Estimated Unit Cost')
    
    # Category information for grouping
    category_id = fields.Many2one('boq.category', string='BOQ Category')
    product_category_id = fields.Many2one('product.category', string='Product Category')
    
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
    
    # Display flags
    has_warning = fields.Boolean(string='Has Warning', compute='_compute_quantity_status', store=False)
    
    @api.depends('category_id', 'category_id.sequence')
    def _compute_category_sequence(self):
        for record in self:
            record.category_sequence = record.category_id.sequence if record.category_id else 999
    
    @api.depends('requested_quantity', 'estimated_cost')
    def _compute_total_cost(self):
        for record in self:
            record.total_cost = record.requested_quantity * record.estimated_cost
    
    @api.depends('requested_quantity', 'remaining_quantity')
    def _compute_quantity_status(self):
        for record in self:
            if record.remaining_quantity <= 0:
                record.quantity_status = 'complete'
                record.has_warning = False
            elif record.requested_quantity > record.remaining_quantity:
                record.quantity_status = 'exceed'
                record.has_warning = True
            else:
                record.quantity_status = 'within'
                record.has_warning = False
    
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
            self.category_id = self.boq_line_id.category_id
            if self.boq_line_id.product_id:
                self.product_category_id = self.boq_line_id.product_id.categ_id
    
    @api.constrains('requested_quantity')
    def _check_requested_quantity(self):
        """Validate requested quantity"""
        for record in self:
            if record.requested_quantity < 0:
                raise ValidationError(_('Requested quantity cannot be negative for line: %s') % record.description)
    

    
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
