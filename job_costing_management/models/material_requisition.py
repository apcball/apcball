# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class MaterialRequisition(models.Model):
    _name = 'material.requisition'
    _description = 'Material Requisition'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name desc'

    name = fields.Char(string='Requisition Number', required=True, copy=False, readonly=True,
                      default=lambda self: _('New'))
    
    # Relations
    project_id = fields.Many2one('project.project', string='Project', required=True)
    job_order_id = fields.Many2one('job.order', string='Job Order')
    job_cost_sheet_id = fields.Many2one('job.cost.sheet', string='Job Cost Sheet')  # Add job cost sheet link
    boq_id = fields.Many2one('boq.boq', string='BOQ Reference')
    employee_id = fields.Many2one('hr.employee', string='Requested by', 
                                 default=lambda self: self.env.user.employee_id)
    department_id = fields.Many2one('hr.department', string='Department',
                                   related='employee_id.department_id', store=True)
    
    # State management
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('dept_approved', 'Department Approved'),
        ('approved', 'Approved'),
        ('ordered', 'Ordered'),
        ('received', 'Received'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='draft', tracking=True)
    
    # Dates
    request_date = fields.Date(string='Request Date', default=fields.Date.today)
    requisition_date = fields.Date(string='Requisition Date', default=fields.Date.today)
    required_date = fields.Date(string='Required Date', required=True)
    approved_date = fields.Date(string='Approved Date')
    
    # Requisition lines
    line_ids = fields.One2many('material.requisition.line', 'requisition_id', string='Requisition Lines')
    
    # Approval workflow
    dept_manager_id = fields.Many2one('res.users', string='Department Manager')
    requisition_manager_id = fields.Many2one('res.users', string='Requisition Manager')
    dept_approval_date = fields.Date(string='Department Approval Date')
    
    # Other fields
    purpose = fields.Text(string='Purpose/Reason')
    notes = fields.Text(string='Notes')
    priority = fields.Selection([
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('urgent', 'Urgent')
    ], string='Priority', default='normal')
    
    # Smart buttons
    purchase_order_count = fields.Integer(string='Purchase Orders', compute='_compute_purchase_order_count')
    picking_count = fields.Integer(string='Pickings', compute='_compute_picking_count')
    
    # Total cost computation
    total_cost = fields.Float(string='Total Cost', compute='_compute_total_amount', store=True)
    
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    
    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('material.requisition') or _('New')
        result = super(MaterialRequisition, self).create(vals)
        return result
    
    def _compute_purchase_order_count(self):
        for record in self:
            # Since we don't have direct linking, we can search for POs by origin
            purchase_orders = self.env['purchase.order'].search([('origin', '=', record.name)])
            record.purchase_order_count = len(purchase_orders)
    
    def _compute_picking_count(self):
        for record in self:
            # Get all picking IDs from requisition lines
            picking_ids = record.line_ids.mapped('picking_ids.id')
            # Also search for pickings by origin
            pickings_by_origin = self.env['stock.picking'].search([('origin', '=', record.name)])
            picking_ids.extend(pickings_by_origin.ids)
            # Remove duplicates
            picking_ids = list(set(picking_ids))
            
            # Debug: Log the picking count
            import logging
            _logger = logging.getLogger(__name__)
            _logger.info(f"Material Requisition {record.name}: Computed {len(picking_ids)} pickings")
            
            record.picking_count = len(picking_ids)
    
    def _compute_total_amount(self):
        """Compute total amount from requisition lines"""
        for record in self:
            record.total_cost = sum(record.line_ids.mapped('total_cost'))
    
    def action_submit(self):
        if not self.line_ids:
            raise ValidationError(_('Please add at least one requisition line.'))
        self.write({'state': 'submitted'})
    
    def action_dept_approve(self):
        self.write({
            'state': 'dept_approved',
            'dept_approval_date': fields.Date.today(),
            'dept_manager_id': self.env.user.id
        })
    
    def action_approve(self):
        self.write({
            'state': 'approved',
            'approved_date': fields.Date.today(),
            'requisition_manager_id': self.env.user.id
        })
    
    def action_reject(self):
        self.write({'state': 'rejected'})
    
    def action_cancel(self):
        self.write({'state': 'cancelled'})
    
    def action_reset_to_draft(self):
        self.write({'state': 'draft'})
    
    def action_create_purchase_order(self):
        # Check if there are any purchase lines
        purchase_lines = self.line_ids.filtered(lambda l: l.requisition_action == 'purchase' and l.vendor_id)
        if not purchase_lines:
            raise ValidationError(_('No purchase lines found with vendors assigned.'))
        
        # Group lines by vendor
        vendor_lines = {}
        for line in purchase_lines:
            if line.vendor_id not in vendor_lines:
                vendor_lines[line.vendor_id] = []
            vendor_lines[line.vendor_id].append(line)
        
        purchase_orders = []
        for vendor, lines in vendor_lines.items():
            po_vals = {
                'partner_id': vendor.id,
                'origin': self.name,
                'material_requisition_id': self.id,  # Link to material requisition
                'job_cost_sheet_id': self.job_cost_sheet_id.id if self.job_cost_sheet_id else False,  # Pass job cost sheet
                'order_line': []
            }
            
            for line in lines:
                po_line_vals = {
                    'product_id': line.product_id.id,
                    'name': line.description,
                    'product_qty': line.quantity,
                    'product_uom': line.uom_id.id,
                    'price_unit': line.estimated_cost,
                    'material_requisition_line_id': line.id,  # Link to requisition line
                    'job_cost_sheet_id': self.job_cost_sheet_id.id if self.job_cost_sheet_id else False,  # Pass job cost sheet
                    'job_cost_line_id': line.job_cost_line_id.id if line.job_cost_line_id else False,  # Pass job cost line
                }
                po_vals['order_line'].append((0, 0, po_line_vals))
            
            if po_vals['order_line']:
                try:
                    po = self.env['purchase.order'].create(po_vals)
                    purchase_orders.append(po.id)
                except Exception as e:
                    raise ValidationError(_('Error creating purchase order for vendor %s: %s') % (vendor.name, str(e)))
        
        if purchase_orders:
            self.write({'state': 'ordered'})
            
            # Use our custom purchase order view to avoid approval_state errors
            tree_view = self.env.ref('job_costing_management.view_purchase_order_tree_job_costing', False)
            
            return {
                'name': 'Purchase Orders',
                'type': 'ir.actions.act_window',
                'res_model': 'purchase.order',
                'view_mode': 'tree,form',
                'views': [(tree_view.id if tree_view else False, 'tree'), (False, 'form')],
                'domain': [('id', 'in', purchase_orders)],
                'context': {'res_model': 'purchase.order'},
            }
    
    def action_create_picking(self):
        internal_lines = self.line_ids.filtered(lambda l: l.requisition_action == 'internal')
        if not internal_lines:
            raise ValidationError(_('No internal transfer lines found.'))
        
        # Get destination location
        dest_location = None
        if hasattr(self.employee_id, 'dest_location_id') and self.employee_id.dest_location_id:
            dest_location = self.employee_id.dest_location_id.id
        elif hasattr(self.department_id, 'dest_location_id') and self.department_id.dest_location_id:
            dest_location = self.department_id.dest_location_id.id
        else:
            # Default to stock location if no specific destination is set
            try:
                dest_location = self.env.ref('stock.stock_location_stock').id
            except ValueError:
                # If stock location doesn't exist, find the first available location
                locations = self.env['stock.location'].search([('usage', '=', 'internal')], limit=1)
                if locations:
                    dest_location = locations[0].id
                else:
                    raise ValidationError(_('No destination location found. Please configure a destination location for the employee or department.'))
        
        # Get source location
        try:
            source_location = self.env.ref('stock.stock_location_stock').id
        except ValueError:
            # If stock location doesn't exist, find the first available location
            locations = self.env['stock.location'].search([('usage', '=', 'internal')], limit=1)
            if locations:
                source_location = locations[0].id
            else:
                raise ValidationError(_('No source location found.'))
        
        # Get internal picking type
        try:
            picking_type = self.env.ref('stock.picking_type_internal').id
        except ValueError:
            # If default internal picking type doesn't exist, find one
            picking_types = self.env['stock.picking.type'].search([('code', '=', 'internal')], limit=1)
            if picking_types:
                picking_type = picking_types[0].id
            else:
                raise ValidationError(_('No internal picking type found.'))
        
        # Create internal transfer
        picking_vals = {
            'picking_type_id': picking_type,
            'location_id': source_location,
            'location_dest_id': dest_location,
            'origin': self.name,
            'move_ids': []
        }
        
        for line in internal_lines:
            move_vals = {
                'name': line.description,
                'product_id': line.product_id.id,
                'product_uom_qty': line.quantity,
                'product_uom': line.uom_id.id,
                'location_id': source_location,
                'location_dest_id': dest_location,
                # Don't set material_requisition_line_id as it doesn't exist in stock.move
            }
            picking_vals['move_ids'].append((0, 0, move_vals))
        
        if picking_vals['move_ids']:
            picking = self.env['stock.picking'].create(picking_vals)
            
            # Link the picking to the requisition lines
            for line in internal_lines:
                line.picking_ids = [(4, picking.id)]
            
            picking.action_confirm()
            picking.action_assign()
            
            # Return action to show the created picking
            return {
                'name': _('Internal Transfer'),
                'type': 'ir.actions.act_window',
                'res_model': 'stock.picking',
                'res_id': picking.id,
                'view_mode': 'form',
                'target': 'current',
            }
        else:
            raise ValidationError(_('No move lines created for internal transfer.'))
    
    def action_received(self):
        self.write({'state': 'received'})
    
    def action_view_purchase_orders(self):
        # Search for purchase orders by origin since we don't have direct linking
        purchase_orders = self.env['purchase.order'].search([('origin', '=', self.name)])
        po_ids = purchase_orders.ids
        
        # Use standard purchase order views
        return {
            'name': 'Purchase Orders',
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', po_ids)],
            'context': {'res_model': 'purchase.order'},
        }
    
    def action_view_pickings(self):
        # Get all picking IDs from requisition lines
        picking_ids = self.line_ids.mapped('picking_ids.id')
        # Also search for pickings by origin
        pickings_by_origin = self.env['stock.picking'].search([('origin', '=', self.name)])
        picking_ids.extend(pickings_by_origin.ids)
        # Remove duplicates
        picking_ids = list(set(picking_ids))
        
        # Debug: Log the picking IDs
        import logging
        _logger = logging.getLogger(__name__)
        _logger.info(f"Material Requisition {self.name}: Found {len(picking_ids)} pickings: {picking_ids}")
        
        return {
            'name': 'Internal Transfers',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', picking_ids)],
            'context': {'default_picking_type_code': 'internal'},
        }


class MaterialRequisitionLine(models.Model):
    _name = 'material.requisition.line'
    _description = 'Material Requisition Line'
    _order = 'sequence, id'

    requisition_id = fields.Many2one('material.requisition', string='Requisition', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)
    
    # Product information
    product_id = fields.Many2one('product.product', string='Product', required=True)
    description = fields.Char(string='Description', required=True)
    quantity = fields.Float(string='Quantity', default=1.0, required=True)
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure')
    
    # Cost information
    estimated_cost = fields.Float(string='Estimated Unit Cost')
    total_cost = fields.Float(string='Total Cost', compute='_compute_total_cost', store=True)
    
    # Requisition action
    requisition_action = fields.Selection([
        ('purchase', 'Purchase Order'),
        ('internal', 'Internal Picking')
    ], string='Requisition Action', default='purchase', required=True)
    
    # Vendor information (for purchase)
    vendor_id = fields.Many2one('res.partner', string='Vendor',
                               domain=[('is_company', '=', True), ('supplier_rank', '>', 0)])
    
    # Relations
    # purchase_order_line_ids = fields.One2many('purchase.order.line', 'material_requisition_line_id', 
    #                                          string='Purchase Order Lines')
    picking_ids = fields.Many2many('stock.picking', string='Pickings')
    boq_line_id = fields.Many2one('boq.line', string='BOQ Line')
    job_cost_line_id = fields.Many2one('job.cost.line', string='Job Cost Line')  # Add job cost line link
    
    # Related fields for easier access
    requisition_state = fields.Selection(related='requisition_id.state', string='Requisition State', readonly=True)
    
    # BOQ tracking fields
    boq_remaining_qty = fields.Float(string='BOQ Remaining Qty', related='boq_line_id.remaining_qty', readonly=True)
    boq_total_qty = fields.Float(string='BOQ Total Qty', related='boq_line_id.adjusted_quantity', readonly=True)
    boq_requisitioned_qty = fields.Float(string='BOQ Requisitioned Qty', related='boq_line_id.total_requisitioned_qty', readonly=True)
    
    # Notes
    notes = fields.Text(string='Notes')
    
    @api.depends('quantity', 'estimated_cost')
    def _compute_total_cost(self):
        for record in self:
            record.total_cost = record.quantity * record.estimated_cost
    
    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.description = self.product_id.name
            self.uom_id = self.product_id.uom_id
            self.estimated_cost = self.product_id.standard_price
            
            # Get preferred vendor
            seller = self.product_id.seller_ids[:1]
            if seller:
                self.vendor_id = seller.partner_id
                self.estimated_cost = seller.price
    
    @api.onchange('quantity', 'boq_line_id')
    def _onchange_quantity_boq_check(self):
        """Check quantity against BOQ remaining quantity and show warning"""
        if self.boq_line_id and self.quantity:
            remaining_qty = self.boq_line_id.remaining_qty
            
            if self.quantity > remaining_qty:
                # Show warning but don't prevent the action
                warning_msg = _(
                    'Warning: Requisition quantity (%s %s) exceeds remaining BOQ quantity (%s %s).\n'
                    'BOQ Total: %s %s\n'
                    'Already Requisitioned: %s %s\n'
                    'Remaining: %s %s\n\n'
                    'You can still proceed with this requisition if needed.'
                ) % (
                    self.quantity, self.uom_id.name or '',
                    remaining_qty, self.boq_line_id.uom_id.name,
                    self.boq_line_id.adjusted_quantity, self.boq_line_id.uom_id.name,
                    self.boq_line_id.total_requisitioned_qty, self.boq_line_id.uom_id.name,
                    remaining_qty, self.boq_line_id.uom_id.name
                )
                
                return {
                    'warning': {
                        'title': _('BOQ Quantity Exceeded'),
                        'message': warning_msg
                    }
                }
    
    @api.onchange('requisition_action')
    def _onchange_requisition_action(self):
        if self.requisition_action == 'internal':
            self.vendor_id = False
