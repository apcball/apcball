# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class PurchaseRequisition(models.Model):
    """Class for adding fields and functions for purchase requisition model."""
    _name = 'employee.purchase.requisition'
    _description = 'Employee Purchase Requisition'
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(string="Reference No", readonly=True)
    employee_id = fields.Many2one(
        comodel_name='hr.employee',
        string='Employee',
        required=True,
        help='Select an employee'
    )
    dept_id = fields.Many2one(
        comodel_name='hr.department',
        string='Department',
        related='employee_id.department_id',
        store=True,
        help='Select an department'
    )
    user_id = fields.Many2one(
        comodel_name='res.users',
        string='Responsible',
        required=True,
        domain=lambda self: [('share', '=', False), ('id', '!=', self.env.uid)],
        help='Select a user who is responsible for requisition'
    )
    
    manager_user_id = fields.Many2one(
        comodel_name='res.users',
        string='Head',
        help='Manager who will approve the requisition'
    )
    requisition_date = fields.Date(
        string="Requisition Date",
        default=lambda self: fields.Date.today(),
        help='Date of requisition'
    )
    receive_date = fields.Date(
        string="Received Date",
        readonly=True,
        help='Received date'
    )
    requisition_deadline = fields.Date(
        string="Requisition Deadline",
        help="End date of purchase requisition"
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        default=lambda self: self.env.company,
        help='Select a company'
    )
    requisition_order_ids = fields.One2many(
        comodel_name='requisition.order',
        inverse_name='requisition_product_id',
        string='Requisition Lines',
        required=True
    )
    confirm_id = fields.Many2one(
        comodel_name='res.users',
        string='Confirmed By',
        default=lambda self: self.env.uid,
        readonly=True,
        help='User who confirmed the requisition.'
    )
    manager_id = fields.Many2one(
        comodel_name='res.users',
        string='Purchase Manager',
        readonly=True,
        help='Purchase manager who approved'
    )
    requisition_head_id = fields.Many2one(
        comodel_name='res.users',
        string='Head Approved By',
        readonly=True,
        help='Department head who approved the requisition.'
    )
    rejected_user_id = fields.Many2one(
        comodel_name='res.users',
        string='Rejected By',
        readonly=True,
        help='User who rejected the requisition'
    )
    confirmed_date = fields.Date(
        string='Confirmed Date',
        readonly=True,
        help='Date of requisition confirmation'
    )
    department_approval_date = fields.Date(
        string='Purchase Approval Date',
        readonly=True,
        help='Purchase approval date'
    )
    approval_date = fields.Date(
        string='Head Approved Date',
        readonly=True,
        help='Head approval date'
    )
    reject_date = fields.Date(
        string='Rejection Date',
        readonly=True,
        help='Requisition rejected date'
    )
    source_location_id = fields.Many2one(
        comodel_name='stock.location',
        string='Source Location',
        help='Source location of requisition.'
    )
    destination_location_id = fields.Many2one(
        comodel_name='stock.location',
        string="Destination Location",
        help='Destination location of requisition.'
    )
    delivery_type_id = fields.Many2one(
        comodel_name='stock.picking.type',
        string='Delivery To',
        help='Type of delivery.'
    )
    internal_picking_id = fields.Many2one(
        comodel_name='stock.picking.type',
        string="Internal Picking"
    )
    requisition_description = fields.Text(string="Reason For Requisition")
    purchase_count = fields.Integer(
        string='Purchase Count',
        help='Purchase count',
        compute='_compute_purchase_count'
    )
    internal_transfer_count = fields.Integer(
        string='Internal Transfer count',
        help='Internal transfer count',
        compute='_compute_internal_transfer_count'
    )
    state = fields.Selection([
        ('new', 'New'),
        ('waiting_head_approval', 'Waiting Head Approval'),
        ('waiting_purchase_approval', 'Waiting Purchase Approval'),
        ('approved', 'Approved'),
        ('purchase_order_created', 'Purchase Order Created'),
        ('received', 'Received'),
        ('cancelled', 'Cancelled')
    ], default='new', copy=False, tracking=True)

    user_is_head = fields.Boolean(
        string="Is Department Head",
        compute="_compute_user_is_head",
        help="Check if current user is department head"
    )
    user_is_purchase = fields.Boolean(
        string="Is Purchase Manager",
        compute="_compute_user_is_purchase",
        help="Check if current user is purchase manager"
    )

    @api.depends('dept_id')
    def _compute_user_is_head(self):
        """Computes if current user is department head"""
        for rec in self:
            rec.user_is_head = self.env.user.has_group('employee_purchase_requisition.employee_requisition_manager')

    @api.depends('dept_id')
    def _compute_user_is_purchase(self):
        """Computes if current user is purchase manager"""
        for rec in self:
            rec.user_is_purchase = self.env.user.has_group('employee_purchase_requisition.employee_requisition_head')

    @api.model
    def create(self, vals):
        """Function to generate purchase requisition sequence"""
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code(
                'employee.purchase.requisition') or 'New'
        result = super(PurchaseRequisition, self).create(vals)
        return result

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        """When employee is selected, get their manager"""
        if self.employee_id and self.employee_id.parent_id:
            # Get the user associated with the manager (parent_id)
            manager_user = self.env['res.users'].search([
                ('employee_id', '=', self.employee_id.parent_id.id)
            ], limit=1)
            if manager_user:
                self.manager_user_id = manager_user.id

    def action_confirm_requisition(self):
        """Function to submit to purchase approval"""
        self.source_location_id = (
            self.employee_id.department_id.department_location_id.id) if (
            self.employee_id.department_id.department_location_id) else (
            self.env.ref('stock.stock_location_stock').id)
        # Only set destination_location_id if not already set by user
        if not self.destination_location_id:
            self.destination_location_id = (
                self.employee_id.employee_location_id.id) if (
                self.employee_id.employee_location_id) else (
                self.env.ref('stock.stock_location_stock').id)
        self.delivery_type_id = (
            self.source_location_id.warehouse_id.in_type_id.id)
        self.internal_picking_id = (
            self.source_location_id.warehouse_id.int_type_id.id)
        self.write({'state': 'waiting_head_approval'})
        self.confirm_id = self.env.uid
        self.confirmed_date = fields.Date.today()

    def action_head_approval(self):
        """Approval from department head"""
        self.write({'state': 'waiting_purchase_approval'})
        self.requisition_head_id = self.env.uid
        self.approval_date = fields.Date.today()

    def action_head_cancel(self):
        """Cancellation from department head"""
        self.write({'state': 'cancelled'})
        self.rejected_user_id = self.env.uid
        self.reject_date = fields.Date.today()

    def action_purchase_approval(self):
        """Approval from purchase department"""
        for rec in self.requisition_order_ids:
            if not rec.partner_id:
                raise ValidationError('Please select vendor for purchase items')
        self.write({'state': 'approved'})
        self.manager_id = self.env.uid
        self.department_approval_date = fields.Date.today()

    def action_purchase_cancel(self):
        """Cancellation from purchase department"""
        self.write({'state': 'cancelled'})
        self.rejected_user_id = self.env.uid
        self.reject_date = fields.Date.today()

    def action_create_purchase_order(self):
        """Create purchase order"""
        purchase_orders = {}

        for rec in self.requisition_order_ids:
            if not rec.partner_id:
                raise ValidationError('Please select vendor for all purchase items')

            vendor_id = rec.partner_id.id
            if vendor_id not in purchase_orders:
                purchase_orders[vendor_id] = []

            line_vals = {
                'name': rec.product_id.name,
                'product_id': rec.product_id.id,
                'product_qty': rec.quantity,
                'product_uom': rec.product_id.uom_po_id.id,
                'date_planned': fields.Date.today(),
                'price_unit': rec.unit_price or rec.product_id.standard_price,
            }
            
            # Only add analytic distribution if it exists
            if rec.analytic_distribution:
                line_vals['analytic_distribution'] = rec.analytic_distribution
            
            purchase_orders[vendor_id].append(line_vals)

        # สร้าง Purchase Orders
        for vendor_id, lines in purchase_orders.items():
            order_lines = [(0, 0, line) for line in lines]
            picking_type_id = False
            if self.destination_location_id and self.destination_location_id.warehouse_id:
                picking_type_id = self.destination_location_id.warehouse_id.in_type_id.id
            self.env['purchase.order'].create({
                'partner_id': vendor_id,
                'requisition_order': self.name,
                'employee_id': self.employee_id.id,
                'dept_id': self.dept_id.id,
                'pr_number': self.name,
                'date_order': fields.Date.today(),
                'order_line': order_lines,
                'destination_location_id': self.destination_location_id.id,
                'picking_type_id': picking_type_id,
            })

        if purchase_orders:
            self.write({'state': 'purchase_order_created'})

    def _compute_internal_transfer_count(self):
        """Function to compute the transfer count"""
        for rec in self:
            rec.internal_transfer_count = self.env['stock.picking'].search_count([
                ('requisition_order', '=', rec.name)])

    def _compute_purchase_count(self):
        """Function to compute the purchase count"""
        for rec in self:
            rec.purchase_count = self.env['purchase.order'].search_count([
                ('requisition_order', '=', rec.name)])

    def action_receive(self):
        """Received purchase requisition by Department Head"""
        if not self.env.user.has_group('employee_purchase_requisition.employee_requisition_manager'):
            raise ValidationError('Only Department Head can mark as received.')
        self.write({'state': 'received'})
        self.receive_date = fields.Date.today()

    def get_purchase_order(self):
        """Purchase order smart button view"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Purchase Order',
            'view_mode': 'tree,form',
            'res_model': 'purchase.order',
            'domain': [('requisition_order', '=', self.name)],
        }

    def get_internal_transfer(self):
        """Internal transfer smart tab view"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Internal Transfers',
            'view_mode': 'tree,form',
            'res_model': 'stock.picking',
            'domain': [('requisition_order', '=', self.name)],
        }