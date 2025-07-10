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
    
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    
    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('material.requisition') or _('New')
        result = super(MaterialRequisition, self).create(vals)
        return result
    
    def _compute_purchase_order_count(self):
        for record in self:
            po_lines = record.line_ids.mapped('purchase_order_line_ids')
            record.purchase_order_count = len(po_lines.mapped('order_id'))
    
    def _compute_picking_count(self):
        for record in self:
            record.picking_count = len(record.line_ids.mapped('picking_ids'))
    
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
        # Group lines by vendor
        vendor_lines = {}
        for line in self.line_ids.filtered(lambda l: l.requisition_action == 'purchase' and l.vendor_id):
            if line.vendor_id not in vendor_lines:
                vendor_lines[line.vendor_id] = []
            vendor_lines[line.vendor_id].append(line)
        
        purchase_orders = []
        for vendor, lines in vendor_lines.items():
            po_vals = {
                'partner_id': vendor.id,
                'origin': self.name,
                'material_requisition_id': self.id,
                'order_line': []
            }
            
            for line in lines:
                po_line_vals = {
                    'product_id': line.product_id.id,
                    'name': line.description,
                    'product_qty': line.quantity,
                    'product_uom': line.uom_id.id,
                    'price_unit': line.estimated_cost,
                    'material_requisition_line_id': line.id,
                }
                po_vals['order_line'].append((0, 0, po_line_vals))
            
            if po_vals['order_line']:
                po = self.env['purchase.order'].create(po_vals)
                purchase_orders.append(po.id)
        
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
            return
        
        # Create internal transfer
        picking_vals = {
            'picking_type_id': self.env.ref('stock.picking_type_internal').id,
            'location_id': self.env.ref('stock.stock_location_stock').id,
            'location_dest_id': self.employee_id.dest_location_id.id or self.department_id.dest_location_id.id,
            'origin': self.name,
            'material_requisition_id': self.id,
            'move_ids': []
        }
        
        for line in internal_lines:
            move_vals = {
                'name': line.description,
                'product_id': line.product_id.id,
                'product_uom_qty': line.quantity,
                'product_uom': line.uom_id.id,
                'location_id': picking_vals['location_id'],
                'location_dest_id': picking_vals['location_dest_id'],
                'material_requisition_line_id': line.id,
            }
            picking_vals['move_ids'].append((0, 0, move_vals))
        
        if picking_vals['move_ids']:
            picking = self.env['stock.picking'].create(picking_vals)
            picking.action_confirm()
            picking.action_assign()
    
    def action_received(self):
        self.write({'state': 'received'})
    
    def action_view_purchase_orders(self):
        po_lines = self.line_ids.mapped('purchase_order_line_ids')
        po_ids = po_lines.mapped('order_id.id')
        
        # Use our custom purchase order view to avoid approval_state errors
        tree_view = self.env.ref('job_costing_management.view_purchase_order_tree_job_costing', False)
        
        return {
            'name': 'Purchase Orders',
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'view_mode': 'tree,form',
            'views': [(tree_view.id if tree_view else False, 'tree'), (False, 'form')],
            'domain': [('id', 'in', po_ids)],
            'context': {'res_model': 'purchase.order'},
        }
    
    def action_view_pickings(self):
        picking_ids = self.line_ids.mapped('picking_ids.id')
        
        return {
            'name': 'Internal Transfers',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', picking_ids)],
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
    purchase_order_line_ids = fields.One2many('purchase.order.line', 'material_requisition_line_id', 
                                             string='Purchase Order Lines')
    picking_ids = fields.Many2many('stock.picking', string='Pickings')
    boq_line_id = fields.Many2one('boq.line', string='BOQ Line')
    
    # Related fields for easier access
    requisition_state = fields.Selection(related='requisition_id.state', string='Requisition State', readonly=True)
    
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
    
    @api.onchange('requisition_action')
    def _onchange_requisition_action(self):
        if self.requisition_action == 'internal':
            self.vendor_id = False
