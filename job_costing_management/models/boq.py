# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class BOQ(models.Model):
    _name = 'boq.boq'
    _description = 'Bill of Quantities (BOQ)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name desc'

    name = fields.Char(string='BOQ Reference', required=True, copy=False, readonly=True,
                      default=lambda self: _('New'))
    
    # Relations
    project_id = fields.Many2one('project.project', string='Project', required=True)
    job_order_id = fields.Many2one('job.order', string='Job Order')
    job_cost_sheet_id = fields.Many2one('job.cost.sheet', string='Job Cost Sheet')
    
    # BOQ Information
    title = fields.Char(string='BOQ Title', required=True)
    description = fields.Text(string='Description')
    boq_date = fields.Date(string='BOQ Date', default=fields.Date.today)
    revision = fields.Char(string='Revision', default='1.0')
    
    # State management
    state = fields.Selection([
        ('draft', 'Draft'),
        ('approved', 'Approved'),
        ('locked', 'Locked'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='draft', tracking=True)
    
    # BOQ Lines
    line_ids = fields.One2many('boq.line', 'boq_id', string='BOQ Lines')
    
    # Categories
    category_ids = fields.One2many('boq.category', 'boq_id', string='Categories')
    
    # Totals
    total_quantity = fields.Float(string='Total Quantity', compute='_compute_totals', store=True)
    total_cost = fields.Float(string='Total Cost', compute='_compute_totals', store=True)
    
    # Smart buttons
    requisition_count = fields.Integer(string='Requisitions', compute='_compute_requisition_count')
    
    # Template relation
    template_id = fields.Many2one('boq.template', string='Created from Template')
    
    # Other fields
    prepared_by = fields.Many2one('res.users', string='Prepared by', default=lambda self: self.env.user)
    approved_by = fields.Many2one('res.users', string='Approved by')
    approved_date = fields.Date(string='Approved Date')
    
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', string='Currency', 
                                 default=lambda self: self.env.company.currency_id)
    
    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('boq.boq') or _('New')
        
        # Handle template creation
        template_id = vals.get('template_id') or self.env.context.get('default_template_id')
        if template_id:
            template = self.env['boq.template'].browse(template_id)
            if template.exists():
                vals['template_id'] = template_id
                # Set title and description from template if not provided
                if not vals.get('title'):
                    vals['title'] = template.name
                if not vals.get('description'):
                    vals['description'] = template.description
        
        result = super(BOQ, self).create(vals)
        
        # Create BOQ lines from template lines
        if template_id:
            template = self.env['boq.template'].browse(template_id)
            if template.exists():
                result._create_lines_from_template(template)
        
        return result
    
    def _create_lines_from_template(self, template):
        """Create BOQ lines from template lines"""
        BOQLine = self.env['boq.line']
        
        # Debug logging
        import logging
        _logger = logging.getLogger(__name__)
        _logger.info(f"Creating BOQ lines from template: {template.name}")
        _logger.info(f"Template has {len(template.line_ids)} lines")
        
        for template_line in template.line_ids:
            _logger.info(f"Processing template line: {template_line.description}, Product: {template_line.product_id.name if template_line.product_id else 'None'}")
            
            line_vals = {
                'boq_id': self.id,
                'sequence': template_line.sequence,
                'item_code': template_line.item_code,
                'product_id': template_line.product_id.id if template_line.product_id else False,
                'description': template_line.description,
                'specification': template_line.specification,
                'quantity': template_line.quantity,
                'uom_id': template_line.uom_id.id if template_line.uom_id else False,
                'unit_cost': template_line.unit_cost,
                'waste_percentage': template_line.waste_percentage,
                'contingency_percentage': template_line.contingency_percentage,
                'notes': template_line.notes,
            }
            new_line = BOQLine.create(line_vals)
            _logger.info(f"Created BOQ line: {new_line.id}, Product: {new_line.product_id.name if new_line.product_id else 'None'}")
    
    @api.depends('line_ids.quantity', 'line_ids.total_cost')
    def _compute_totals(self):
        for record in self:
            record.total_quantity = sum(record.line_ids.mapped('quantity'))
            record.total_cost = sum(record.line_ids.mapped('total_cost'))
    
    def _compute_requisition_count(self):
        for record in self:
            record.requisition_count = len(record.line_ids.mapped('requisition_line_ids.requisition_id'))
    
    def action_approve(self):
        self.write({
            'state': 'approved',
            'approved_by': self.env.user.id,
            'approved_date': fields.Date.today()
        })
    
    def action_lock(self):
        self.write({'state': 'locked'})
    
    def action_cancel(self):
        self.write({'state': 'cancelled'})
    
    def action_reset_to_draft(self):
        self.write({'state': 'draft'})
    
    def action_create_material_requisition(self):
        """Create material requisition from BOQ lines"""
        if not self.line_ids:
            raise ValidationError(_('No BOQ lines to create requisition from.'))
        
        # Group lines by category or create single requisition
        requisition_vals = {
            'project_id': self.project_id.id,
            'job_order_id': self.job_order_id.id,
            'boq_id': self.id,
            'purpose': f'Material requisition from BOQ: {self.name}',
            'line_ids': []
        }
        
        for line in self.line_ids.filtered(lambda l: l.product_id):
            req_line_vals = {
                'product_id': line.product_id.id,
                'description': line.description,
                'quantity': line.quantity,
                'uom_id': line.uom_id.id,
                'estimated_cost': line.unit_cost,
                'boq_line_id': line.id,
            }
            requisition_vals['line_ids'].append((0, 0, req_line_vals))
        
        if requisition_vals['line_ids']:
            requisition = self.env['material.requisition'].create(requisition_vals)
            return {
                'name': 'Material Requisition',
                'type': 'ir.actions.act_window',
                'res_model': 'material.requisition',
                'view_mode': 'form',
                'res_id': requisition.id,
            }
    
    def action_create_job_cost_lines(self):
        """Create job cost lines from BOQ"""
        if not self.job_cost_sheet_id:
            raise ValidationError(_('Please specify a job cost sheet.'))
        
        for line in self.line_ids.filtered(lambda l: l.product_id):
            cost_line_vals = {
                'cost_sheet_id': self.job_cost_sheet_id.id,
                'cost_type': 'material',
                'product_id': line.product_id.id,
                'description': line.description,
                'quantity': line.quantity,
                'uom_id': line.uom_id.id,
                'unit_cost': line.unit_cost,
                'total_cost': line.total_cost,
                'boq_line_id': line.id,
            }
            self.env['job.cost.line'].create(cost_line_vals)
    
    def action_view_requisitions(self):
        requisition_ids = self.line_ids.mapped('requisition_line_ids.requisition_id.id')
        
        return {
            'name': 'Material Requisitions',
            'type': 'ir.actions.act_window',
            'res_model': 'material.requisition',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', requisition_ids)],
        }


class BOQCategory(models.Model):
    _name = 'boq.category'
    _description = 'BOQ Category'
    _order = 'sequence, name'

    name = fields.Char(string='Category Name', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    boq_id = fields.Many2one('boq.boq', string='BOQ', required=True, ondelete='cascade')
    description = fields.Text(string='Description')
    
    # Computed fields
    line_ids = fields.One2many('boq.line', 'category_id', string='BOQ Lines')
    total_cost = fields.Float(string='Total Cost', compute='_compute_total_cost', store=True)
    
    @api.depends('line_ids.total_cost')
    def _compute_total_cost(self):
        for record in self:
            record.total_cost = sum(record.line_ids.mapped('total_cost'))


class BOQLine(models.Model):
    _name = 'boq.line'
    _description = 'BOQ Line'
    _order = 'sequence, id'

    boq_id = fields.Many2one('boq.boq', string='BOQ', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)
    category_id = fields.Many2one('boq.category', string='Category')
    
    # Item information
    item_code = fields.Char(string='Item Code')
    product_id = fields.Many2one('product.product', string='Product')
    description = fields.Text(string='Description', required=True)
    specification = fields.Text(string='Specification')
    
    # Quantity and Unit
    quantity = fields.Float(string='Quantity', default=1.0, required=True)
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure', required=True)
    
    # Cost information
    unit_cost = fields.Float(string='Unit Cost', required=True)
    total_cost = fields.Float(string='Total Cost', compute='_compute_total_cost', store=True)
    
    # Waste and contingency
    waste_percentage = fields.Float(string='Waste %', default=0.0)
    contingency_percentage = fields.Float(string='Contingency %', default=0.0)
    
    # Adjusted quantities and costs
    adjusted_quantity = fields.Float(string='Adjusted Quantity', compute='_compute_adjusted_values', store=True)
    adjusted_total_cost = fields.Float(string='Adjusted Total Cost', compute='_compute_adjusted_values', store=True)
    
    # Relations
    requisition_line_ids = fields.One2many('material.requisition.line', 'boq_line_id', string='Requisition Lines')
    cost_line_ids = fields.One2many('job.cost.line', 'boq_line_id', string='Cost Lines')
    
    # Status
    status = fields.Selection([
        ('pending', 'Pending'),
        ('requisitioned', 'Requisitioned'),
        ('ordered', 'Ordered'),
        ('received', 'Received'),
        ('completed', 'Completed')
    ], string='Status', default='pending', compute='_compute_status', store=True)
    
    # Notes
    notes = fields.Text(string='Notes')
    
    @api.depends('quantity', 'unit_cost')
    def _compute_total_cost(self):
        for record in self:
            record.total_cost = record.quantity * record.unit_cost
    
    @api.depends('quantity', 'waste_percentage', 'contingency_percentage', 'total_cost')
    def _compute_adjusted_values(self):
        for record in self:
            waste_factor = 1 + (record.waste_percentage / 100)
            contingency_factor = 1 + (record.contingency_percentage / 100)
            
            record.adjusted_quantity = record.quantity * waste_factor
            record.adjusted_total_cost = record.total_cost * waste_factor * contingency_factor
    
    @api.depends('requisition_line_ids.requisition_id.state')
    def _compute_status(self):
        for record in self:
            if not record.requisition_line_ids:
                record.status = 'pending'
            else:
                states = record.requisition_line_ids.mapped('requisition_id.state')
                if 'received' in states:
                    record.status = 'received'
                elif 'ordered' in states:
                    record.status = 'ordered'
                elif 'approved' in states:
                    record.status = 'requisitioned'
                else:
                    record.status = 'pending'
    
    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.description = self.product_id.name
            self.uom_id = self.product_id.uom_id
            self.unit_cost = self.product_id.standard_price
            self.item_code = self.product_id.default_code or ''
    
    def action_create_requisition(self):
        """Create material requisition from this BOQ line"""
        requisition_vals = {
            'project_id': self.boq_id.project_id.id,
            'job_order_id': self.boq_id.job_order_id.id,
            'boq_id': self.boq_id.id,
            'purpose': f'Material requisition for BOQ line: {self.description}',
            'line_ids': [(0, 0, {
                'product_id': self.product_id.id,
                'description': self.description,
                'quantity': self.adjusted_quantity,
                'uom_id': self.uom_id.id,
                'estimated_cost': self.unit_cost,
                'boq_line_id': self.id,
            })]
        }
        
        requisition = self.env['material.requisition'].create(requisition_vals)
        return {
            'name': 'Material Requisition',
            'type': 'ir.actions.act_window',
            'res_model': 'material.requisition',
            'view_mode': 'form',
            'res_id': requisition.id,
        }


class BOQTemplate(models.Model):
    _name = 'boq.template'
    _description = 'BOQ Template'
    _order = 'name'

    name = fields.Char(string='Template Name', required=True)
    description = fields.Text(string='Description')
    job_type_id = fields.Many2one('job.type', string='Job Type')
    
    # Template lines
    line_ids = fields.One2many('boq.template.line', 'template_id', string='Template Lines')
    
    # Computed fields
    total_cost = fields.Float(string='Total Cost', compute='_compute_total_cost', store=True)
    
    @api.depends('line_ids.total_cost')
    def _compute_total_cost(self):
        for record in self:
            record.total_cost = sum(record.line_ids.mapped('total_cost'))
    
    def action_create_boq(self):
        """Create BOQ from template"""
        ctx = self.env.context.copy()
        ctx.update({
            'default_template_id': self.id,
            'default_title': self.name,
            'default_description': self.description,
        })
        
        return {
            'name': 'Create BOQ from Template',
            'type': 'ir.actions.act_window',
            'res_model': 'boq.boq',
            'view_mode': 'form',
            'context': ctx,
        }


class BOQTemplateLine(models.Model):
    _name = 'boq.template.line'
    _description = 'BOQ Template Line'
    _order = 'sequence, id'

    template_id = fields.Many2one('boq.template', string='Template', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)
    
    # Item information
    item_code = fields.Char(string='Item Code')
    product_id = fields.Many2one('product.product', string='Product')
    description = fields.Text(string='Description', required=True)
    specification = fields.Text(string='Specification')
    
    # Quantity and Unit
    quantity = fields.Float(string='Quantity', default=1.0, required=True)
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure', required=True)
    
    # Cost information
    unit_cost = fields.Float(string='Unit Cost', required=True)
    total_cost = fields.Float(string='Total Cost', compute='_compute_total_cost', store=True)
    
    # Waste and contingency
    waste_percentage = fields.Float(string='Waste %', default=0.0)
    contingency_percentage = fields.Float(string='Contingency %', default=0.0)
    
    # Notes
    notes = fields.Text(string='Notes')
    
    @api.depends('quantity', 'unit_cost')
    def _compute_total_cost(self):
        for record in self:
            record.total_cost = record.quantity * record.unit_cost
    
    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.description = self.product_id.name
            self.uom_id = self.product_id.uom_id
            self.unit_cost = self.product_id.standard_price
            self.item_code = self.product_id.default_code or ''
