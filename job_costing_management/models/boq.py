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
    
    # Purchase tracking totals
    total_requisitioned_amount = fields.Float(string='Total Requisitioned Amount', compute='_compute_purchase_totals', store=True)
    total_ordered_amount = fields.Float(string='Total Ordered Amount', compute='_compute_purchase_totals', store=True)
    total_received_amount = fields.Float(string='Total Received Amount', compute='_compute_purchase_totals', store=True)
    overall_purchase_progress = fields.Float(string='Overall Purchase Progress (%)', compute='_compute_purchase_totals', store=True)
    
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
                # Validate template has lines with products
                if not template.line_ids:
                    raise ValidationError(_('Template has no lines to copy.'))
                
                lines_without_products = template.line_ids.filtered(lambda l: not l.product_id)
                if lines_without_products:
                    raise ValidationError(_('Template has lines without products. Please ensure all template lines have products assigned.'))
                
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
            
            # Validate that essential fields are present
            if not line_vals['description']:
                _logger.warning(f"Template line {template_line.id} has no description")
                continue
                
            if not line_vals['uom_id']:
                _logger.warning(f"Template line {template_line.id} has no UOM")
                continue
            
            new_line = BOQLine.create(line_vals)
            _logger.info(f"Created BOQ line: {new_line.id}, Product: {new_line.product_id.name if new_line.product_id else 'None'}")
            
            # Additional check: if the created line has no product, log it
            if not new_line.product_id:
                _logger.warning(f"Created BOQ line {new_line.id} has no product assigned")
    
    @api.depends('line_ids.quantity', 'line_ids.total_cost')
    def _compute_totals(self):
        for record in self:
            record.total_quantity = sum(record.line_ids.mapped('quantity'))
            record.total_cost = sum(record.line_ids.mapped('total_cost'))
    
    @api.depends('line_ids.total_requisitioned_qty', 'line_ids.total_ordered_qty', 'line_ids.total_received_qty', 'line_ids.unit_cost', 'line_ids.adjusted_total_cost')
    def _compute_purchase_totals(self):
        for record in self:
            # Calculate total amounts based on quantities and unit costs
            total_req_amount = 0
            total_ord_amount = 0
            total_rec_amount = 0
            total_boq_amount = sum(record.line_ids.mapped('adjusted_total_cost'))
            
            for line in record.line_ids:
                total_req_amount += line.total_requisitioned_qty * line.unit_cost
                total_ord_amount += line.total_ordered_qty * line.unit_cost
                total_rec_amount += line.total_received_qty * line.unit_cost
            
            record.total_requisitioned_amount = total_req_amount
            record.total_ordered_amount = total_ord_amount
            record.total_received_amount = total_rec_amount
            
            # Calculate overall progress
            if total_boq_amount > 0:
                record.overall_purchase_progress = (total_req_amount / total_boq_amount) * 100
            else:
                record.overall_purchase_progress = 0.0
    
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
    
    def action_duplicate(self):
        """Create a duplicate of this BOQ"""
        new_boq = self.copy()
        
        return {
            'name': 'Duplicate BOQ',
            'type': 'ir.actions.act_window',
            'res_model': 'boq.boq',
            'view_mode': 'form',
            'res_id': new_boq.id,
            'target': 'current',
        }
    
    def action_create_material_requisition(self):
        """Create material requisition from BOQ lines"""
        if not self.line_ids:
            raise ValidationError(_('No BOQ lines to create requisition from.'))
        
        # Filter lines that have products and remaining quantities
        lines_with_products = self.line_ids.filtered(lambda l: l.product_id)
        if not lines_with_products:
            raise ValidationError(_('No BOQ lines with products found to create requisition from.'))
        
        # Filter lines with remaining quantities
        lines_with_remaining = lines_with_products.filtered(lambda l: l.remaining_qty > 0)
        if not lines_with_remaining:
            raise ValidationError(_(
                'No BOQ lines with remaining quantities found to create requisition from.\n'
                'All items have already been fully requisitioned.'
            ))
        
        # Group lines by category or create single requisition
        requisition_vals = {
            'project_id': self.project_id.id,
            'job_order_id': self.job_order_id.id if self.job_order_id else False,
            'job_cost_sheet_id': self.job_cost_sheet_id.id if self.job_cost_sheet_id else False,
            'boq_id': self.id,
            'purpose': f'Material requisition from BOQ: {self.name}',
            'required_date': fields.Date.today(),
            'line_ids': []
        }
        
        for line in lines_with_remaining:
            # Find the corresponding job cost line for this BOQ line
            job_cost_line = False
            if line.cost_line_ids:
                job_cost_line = line.cost_line_ids[0]  # Take the first related cost line
            
            req_line_vals = {
                'product_id': line.product_id.id,
                'description': line.description,
                'quantity': line.remaining_qty,  # Use remaining quantity instead of full quantity
                'uom_id': line.uom_id.id,
                'estimated_cost': line.unit_cost,
                'boq_line_id': line.id,
                'job_cost_line_id': job_cost_line.id if job_cost_line else False,
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
        # Debug logging
        import logging
        _logger = logging.getLogger(__name__)
        _logger.info(f"Creating job cost lines from BOQ: {self.name}")
        
        if not self.job_cost_sheet_id:
            raise ValidationError(_('Please specify a job cost sheet.'))
        
        _logger.info(f"Job cost sheet: {self.job_cost_sheet_id.name}")
        
        # Check if there are any BOQ lines with products
        lines_with_products = self.line_ids.filtered(lambda l: l.product_id)
        if not lines_with_products:
            raise ValidationError(_('No BOQ lines with products found to create job cost lines from.'))
        
        _logger.info(f"Found {len(lines_with_products)} BOQ lines with products")
        
        created_lines = []
        skipped_lines = []
        
        for line in lines_with_products:
            _logger.info(f"Processing BOQ line: {line.description}, Product: {line.product_id.name}")
            
            # Check if job cost line already exists for this BOQ line
            existing_line = self.env['job.cost.line'].search([
                ('cost_sheet_id', '=', self.job_cost_sheet_id.id),
                ('boq_line_id', '=', line.id)
            ], limit=1)
            
            if existing_line:
                _logger.info(f"Skipping BOQ line {line.id} - job cost line already exists: {existing_line.id}")
                skipped_lines.append(line.description)
                continue  # Skip if already exists
            
            cost_line_vals = {
                'cost_sheet_id': self.job_cost_sheet_id.id,
                'cost_type': 'material',
                'product_id': line.product_id.id,
                'name': line.description,
                'planned_qty': line.quantity,
                'uom_id': line.uom_id.id,
                'unit_cost': line.unit_cost,
                'boq_line_id': line.id,  # Link to BOQ line
            }
            
            _logger.info(f"Creating job cost line with values: {cost_line_vals}")
            
            try:
                cost_line = self.env['job.cost.line'].create(cost_line_vals)
                created_lines.append(cost_line.id)
                _logger.info(f"Created job cost line: {cost_line.id}")
            except Exception as e:
                _logger.error(f"Error creating job cost line for {line.description}: {str(e)}")
                raise ValidationError(_('Error creating job cost line for %s: %s') % (line.description, str(e)))
        
        if not created_lines:
            if skipped_lines:
                raise ValidationError(_('No new job cost lines were created. The following lines already exist: %s') % ', '.join(skipped_lines))
            else:
                raise ValidationError(_('No new job cost lines were created. They may already exist.'))
        
        _logger.info(f"Successfully created {len(created_lines)} job cost lines")
        
        # Return action to show the created job cost lines
        return {
            'name': _('Job Cost Lines'),
            'type': 'ir.actions.act_window',
            'res_model': 'job.cost.line',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', created_lines)],
            'context': {'res_model': 'job.cost.line'},
        }
    
    def action_view_requisitions(self):
        requisition_ids = self.line_ids.mapped('requisition_line_ids.requisition_id.id')
        
        return {
            'name': 'Material Requisitions',
            'type': 'ir.actions.act_window',
            'res_model': 'material.requisition',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', requisition_ids)],
        }
    
    def action_debug_wizard_access(self):
        """Debug method to check wizard access rights"""
        try:
            # Try to access the wizard model
            wizard_model = self.env['boq.material.requisition.wizard']
            
            # Check if user can create wizard records
            wizard_model.check_access_rights('create')
            wizard_model.check_access_rights('read')
            wizard_model.check_access_rights('write')
            
            # Get user groups
            user_groups = self.env.user.groups_id.mapped('name')
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Wizard Access Check',
                    'message': f'✅ User has access to wizard. Groups: {", ".join(user_groups)}',
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Wizard Access Error',
                    'message': f'❌ Access denied: {str(e)}',
                    'type': 'danger',
                    'sticky': True,
                }
            }
    
    def check_requisition_readiness(self):
        """Check if BOQ is ready for material requisition creation"""
        issues = []
        
        if self.state not in ('approved', 'locked'):
            issues.append(f'BOQ state must be approved or locked (current: {self.state})')
        
        if not self.line_ids:
            issues.append('BOQ has no lines')
        
        lines_without_products = self.line_ids.filtered(lambda l: not l.product_id)
        if lines_without_products:
            issues.append(f'{len(lines_without_products)} BOQ lines have no products assigned')
        
        lines_with_products = self.line_ids.filtered(lambda l: l.product_id)
        lines_with_remaining = lines_with_products.filtered(lambda l: l.remaining_qty > 0)
        
        if not lines_with_remaining:
            if lines_with_products:
                issues.append('All BOQ lines with products have been fully requisitioned')
            else:
                issues.append('No BOQ lines have products assigned')
        
        return {
            'ready': len(issues) == 0,
            'issues': issues,
            'lines_total': len(self.line_ids),
            'lines_with_products': len(lines_with_products),
            'lines_with_remaining': len(lines_with_remaining),
        }
    
    def copy(self, default=None):
        """Override copy method to handle proper duplication of BOQ"""
        if default is None:
            default = {}
        
        # Generate new name for the copy
        if 'name' not in default:
            default['name'] = _('New')
        
        # Update title to indicate it's a copy
        if 'title' not in default:
            default['title'] = _("%s (Copy)") % self.title
        
        # Reset state and approval fields
        default.update({
            'state': 'draft',
            'approved_by': False,
            'approved_date': False,
            'template_id': False,  # Don't copy template reference
        })
        
        # Store original lines and categories
        original_lines = self.line_ids
        original_categories = self.category_ids
        
        # Debug logging
        import logging
        _logger = logging.getLogger(__name__)
        _logger.info(f"Copying BOQ: {self.name}")
        _logger.info(f"Original BOQ has {len(original_lines)} lines")
        
        # Copy the BOQ record using standard copy
        new_boq = super(BOQ, self).copy(default)
        
        # Clear any automatically copied lines that may not have copied properly
        if new_boq.line_ids:
            new_boq.line_ids.unlink()
        if new_boq.category_ids:
            new_boq.category_ids.unlink()
        
        # Copy categories first
        category_mapping = {}
        for category in original_categories:
            category_vals = {
                'boq_id': new_boq.id,
                'sequence': category.sequence,
                'name': category.name,
                'description': category.description,
            }
            new_category = self.env['boq.category'].create(category_vals)
            category_mapping[category.id] = new_category.id
        
        # Manually copy BOQ lines with proper field copying
        for line in original_lines:
            line_vals = {
                'boq_id': new_boq.id,
                'sequence': line.sequence,
                'category_id': category_mapping.get(line.category_id.id) if line.category_id else False,
                'item_code': line.item_code,
                'product_id': line.product_id.id if line.product_id else False,
                'description': line.description,
                'specification': line.specification,
                'quantity': line.quantity,
                'uom_id': line.uom_id.id if line.uom_id else False,
                'unit_cost': line.unit_cost,
                'waste_percentage': line.waste_percentage,
                'contingency_percentage': line.contingency_percentage,
                'notes': line.notes,
                # Reset status and don't copy relations
                'status': 'pending',
            }
            new_line = self.env['boq.line'].create(line_vals)
            _logger.info(f"Created BOQ line copy: {new_line.id}, Product: {new_line.product_id.name if new_line.product_id else 'None'}")
        
        _logger.info(f"BOQ copy completed. New BOQ has {len(new_boq.line_ids)} lines")
        return new_boq


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
    product_id = fields.Many2one('product.product', string='Product', required=True)
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
    
    # Purchase tracking fields
    total_requisitioned_qty = fields.Float(string='Total Requisitioned Qty', compute='_compute_purchase_tracking', store=True)
    total_ordered_qty = fields.Float(string='Total Ordered Qty', compute='_compute_purchase_tracking', store=True)
    total_received_qty = fields.Float(string='Total Received Qty', compute='_compute_purchase_tracking', store=True)
    remaining_qty = fields.Float(string='Remaining Qty', compute='_compute_purchase_tracking', store=True)
    purchase_progress = fields.Float(string='Purchase Progress (%)', compute='_compute_purchase_tracking', store=True)
    
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
    
    @api.depends('requisition_line_ids', 'requisition_line_ids.quantity', 'requisition_line_ids.requisition_state')
    def _compute_purchase_tracking(self):
        """Compute purchase tracking fields"""
        for record in self:
            # Get all requisition lines for this BOQ line
            req_lines = record.requisition_line_ids
            
            # Calculate total requisitioned quantity (all states except cancelled/rejected)
            active_req_lines = req_lines.filtered(lambda l: l.requisition_state not in ['cancelled', 'rejected'])
            record.total_requisitioned_qty = sum(active_req_lines.mapped('quantity'))
            
            # Calculate total ordered quantity (approved and above states)
            ordered_req_lines = req_lines.filtered(lambda l: l.requisition_state in ['approved', 'ordered', 'received'])
            record.total_ordered_qty = sum(ordered_req_lines.mapped('quantity'))
            
            # Calculate total received quantity
            received_req_lines = req_lines.filtered(lambda l: l.requisition_state == 'received')
            record.total_received_qty = sum(received_req_lines.mapped('quantity'))
            
            # Calculate remaining quantity
            record.remaining_qty = record.adjusted_quantity - record.total_requisitioned_qty
            
            # Calculate purchase progress percentage
            if record.adjusted_quantity > 0:
                record.purchase_progress = (record.total_requisitioned_qty / record.adjusted_quantity) * 100
            else:
                record.purchase_progress = 0.0
    
    @api.depends('quantity', 'waste_percentage', 'contingency_percentage', 'total_cost')
    def _compute_adjusted_values(self):
        for record in self:
            waste_factor = 1 + (record.waste_percentage / 100)
            contingency_factor = 1 + (record.contingency_percentage / 100)
            
            record.adjusted_quantity = record.quantity * waste_factor
            record.adjusted_total_cost = record.total_cost * waste_factor * contingency_factor
    
    @api.depends('requisition_line_ids.requisition_id.state', 'total_received_qty', 'adjusted_quantity')
    def _compute_status(self):
        for record in self:
            if not record.requisition_line_ids:
                record.status = 'pending'
            else:
                # Check if fully received
                if record.total_received_qty >= record.adjusted_quantity:
                    record.status = 'completed'
                elif record.total_received_qty > 0:
                    record.status = 'received'
                elif record.total_ordered_qty > 0:
                    record.status = 'ordered'
                elif record.total_requisitioned_qty > 0:
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
        if not self.product_id:
            raise ValidationError(_('Please specify a product for this BOQ line before creating a requisition.'))
        
        # Check remaining quantity
        if self.remaining_qty <= 0:
            raise ValidationError(_(
                'No remaining quantity to requisition for this BOQ line.\n'
                'BOQ Quantity: %s %s\n'
                'Already Requisitioned: %s %s\n'
                'Remaining: %s %s'
            ) % (
                self.adjusted_quantity, self.uom_id.name,
                self.total_requisitioned_qty, self.uom_id.name,
                self.remaining_qty, self.uom_id.name
            ))
        
        # Use remaining quantity as default, but allow user to modify
        default_qty = self.remaining_qty
        
        requisition_vals = {
            'project_id': self.boq_id.project_id.id,
            'job_order_id': self.boq_id.job_order_id.id if self.boq_id.job_order_id else False,
            'job_cost_sheet_id': self.boq_id.job_cost_sheet_id.id if self.boq_id.job_cost_sheet_id else False,
            'boq_id': self.boq_id.id,
            'purpose': f'Material requisition for BOQ line: {self.description}',
            'required_date': fields.Date.today(),
            'line_ids': [(0, 0, {
                'product_id': self.product_id.id,
                'description': self.description,
                'quantity': default_qty,
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
    
    def copy(self, default=None):
        """Override copy method to ensure proper copying of BOQ lines"""
        if default is None:
            default = {}
        
        # Ensure all relational fields are properly copied
        default.update({
            'requisition_line_ids': [],  # Don't copy requisition relations
            'cost_line_ids': [],  # Don't copy cost line relations
            'status': 'pending',  # Reset status
        })
        
        return super(BOQLine, self).copy(default)


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
    
    def copy(self, default=None):
        """Override copy method to handle proper duplication of BOQ Template"""
        if default is None:
            default = {}
        
        # Update name to indicate it's a copy
        if 'name' not in default:
            default['name'] = _("%s (Copy)") % self.name
        
        # Copy the template record
        new_template = super(BOQTemplate, self).copy(default)
        
        # Clear any automatically copied lines that may not have copied properly
        if new_template.line_ids:
            new_template.line_ids.unlink()
        
        # Manually copy template lines with proper field copying
        for line in self.line_ids:
            line_vals = {
                'template_id': new_template.id,
                'sequence': line.sequence,
                'item_code': line.item_code,
                'product_id': line.product_id.id if line.product_id else False,
                'description': line.description,
                'specification': line.specification,
                'quantity': line.quantity,
                'uom_id': line.uom_id.id if line.uom_id else False,
                'unit_cost': line.unit_cost,
                'waste_percentage': line.waste_percentage,
                'contingency_percentage': line.contingency_percentage,
                'notes': line.notes,
            }
            self.env['boq.template.line'].create(line_vals)
        
        return new_template


class BOQTemplateLine(models.Model):
    _name = 'boq.template.line'
    _description = 'BOQ Template Line'
    _order = 'sequence, id'

    template_id = fields.Many2one('boq.template', string='Template', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)
    
    # Item information
    item_code = fields.Char(string='Item Code')
    product_id = fields.Many2one('product.product', string='Product', required=True)
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
    
    def copy(self, default=None):
        """Override copy method to ensure proper copying of BOQ template lines"""
        if default is None:
            default = {}
        
        # Ensure all fields are properly copied
        return super(BOQTemplateLine, self).copy(default)
