# -*- coding: utf-8 -*-
from datetime import timedelta
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class PurchaseRequisition(models.Model):
    """Class for adding fields and functions for purchase requisition model."""
    _name = 'employee.purchase.requisition'
    _description = 'Employee Purchase Requisition'
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(string="Reference No", readonly=True)
    requisition_id = fields.Many2one('employee.purchase.requisition', string="Requisition")
    request_date = fields.Date(string="Requested Date")
    vendor_id = fields.Many2one('res.partner', string="Suggested Vendor")
    location_id = fields.Many2one('stock.location', string="Delivery Location")
    purpose = fields.Text(string="Purpose / Usage")
    purchase_price_unit = fields.Float(string="Purchase Price / Unit")
    purchase_vendor_id = fields.Many2one('res.partner', string="Actual Vendor")
    purchase_order_ref = fields.Char(string="PO Reference")
    name = fields.Char(string="Request Number", required=True, copy=False, readonly=True, default='New')
    request_number = fields.Char(string="Request Number")
    expense_code_id = fields.Many2one('account.analytic.account', string='Expense Code')
    requisition_id = fields.Many2one('employee.purchase.requisition', string="Requisition")
    product_code = fields.Char(string="รหัสสินค้า")
    product_name = fields.Char(string="ชื่อสินค้า")
    request_qty = fields.Float(string="จำนวนขอซื้อ")
    product_uom = fields.Many2one('uom.uom', string="หน่วย")
    price_unit = fields.Float(string="ราคา/หน่วย")
    price_subtotal = fields.Float(string="จำนวนเงินรวม", compute="_compute_price_subtotal")
    request_date = fields.Date(string="วันที่ต้องการ")
    vendor_id = fields.Many2one('res.partner', string="ผู้จัดจำหน่าย")
    delivery_location = fields.Char(string="สถานที่ส่ง/คลัง")
    purpose = fields.Text(string="วัตถุประสงค์")
    purpose = fields.Char(string="Purpose")
    note = fields.Text(string="หมายเหตุ")
   
    employee_id = fields.Many2one(
        comodel_name='hr.employee',
        string='Employee',
        required=True,
        default=lambda self: self._default_employee_id(),
        help='Select an employee'
    )
    expense_code_id = fields.Many2one(
        'account.analytic.account',  # or your actual expense code model
        string='Expense Code'
    )
    dept_id = fields.Many2one(
        comodel_name='hr.department',
        string='Department',
        related='employee_id.department_id',
        store=True,
        help='Select an department'
    )
    request_plan = fields.Date(
    string="Planned Purchase Date"
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
    request_plan = fields.Text(
    string="Request Plan",
    help="Planned usage or purchase justification"
    )
    request_date = fields.Date(
    string='Request Date',
    default=fields.Date.today,
    help='Date of request'
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
    company_currency_id = fields.Many2one(
        related='company_id.currency_id',
        string='Currency',
        readonly=True,
        store=True
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
    total_amount = fields.Float(
        string="Total Amount",
        compute="_compute_total_amount",
        store=True,
        help="Total value of all items in this requisition"
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('waiting_head_approval', 'Waiting Head Approval'),
        ('waiting_purchase_approval', 'Waiting Purchase Approval'),
        ('approved', 'Approved'),
        ('purchase_order_created', 'Purchase Order Created'),
        ('received', 'Received'),
        ('cancelled', 'Cancelled')
    ], default='draft', copy=False, tracking=True)

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
    user_is_requester = fields.Boolean(
        string="Is Requester",
        compute="_compute_user_is_requester",
        help="Check if current user is the original requester"
    )
    
    @api.model
    def _default_employee_id(self):
        """Get the employee record linked to the current user"""
        employee = self.env.user.employee_id
        return employee.id if employee else False
    
    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('employee.purchase.requisition') or 'New'
        
        # Set employee_id from current user if not provided
        if not vals.get('employee_id'):
            employee = self.env.user.employee_id
            if employee:
                vals['employee_id'] = employee.id
        
        return super().create(vals)
    
    @api.onchange('user_id')
    def _onchange_user_id(self):
        """When user is changed, update employee_id if not set"""
        if self.user_id and not self.employee_id:
            employee = self.user_id.employee_id
            if employee:
                self.employee_id = employee.id

    @api.depends('dept_id')
    def _compute_user_is_purchase(self):
        """Computes if current user is purchase manager"""
        for rec in self:
            rec.user_is_purchase = self.env.user.has_group('employee_purchase_requisition.employee_requisition_head')

    def _compute_user_is_requester(self):
        """Check if current user is the original requester"""
        for rec in self:
            rec.user_is_requester = rec.create_uid == self.env.user or rec.employee_id.user_id == self.env.user

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
        # Check if all requisition lines have analytic distribution
        for line in self.requisition_order_ids:
            if not line.analytic_distribution:
                raise ValidationError('Please enter Analytic Distribution for all items before submitting for approval.')
        
        self.source_location_id = (
            self.employee_id.department_id.department_location_id.id) if (
            self.employee_id.department_id.department_location_id) else (
            self.env.ref('stock.stock_location_stock').id)
        # Only set destination_location_id if not already set by user
        if not self.destination_location_id:
            # Check if user has access to employee_location_id field
            try:
                employee_location = self.employee_id.sudo().employee_location_id
                self.destination_location_id = employee_location.id if employee_location else self.env.ref('stock.stock_location_stock').id
            except Exception:
                # Fallback to default location if access is denied
                self.destination_location_id = self.env.ref('stock.stock_location_stock').id
        self.delivery_type_id = (
            self.source_location_id.warehouse_id.in_type_id.id)
        self.internal_picking_id = (
            self.source_location_id.warehouse_id.int_type_id.id)
        self.write({'state': 'waiting_head_approval'})
        self.confirm_id = self.env.uid
        self.confirmed_date = fields.Date.today()
        
        # Create activity for department head
        self._create_head_approval_activity()

    def action_head_approval(self):
        """Approval from department head"""
        self.write({'state': 'waiting_purchase_approval'})
        self.requisition_head_id = self.env.uid
        self.approval_date = fields.Date.today()
        
        # Create activity for responsible person (purchase department)
        self._create_purchase_approval_activity()

    def action_head_cancel(self):
        """Cancellation from department head"""
        self.write({'state': 'draft'})
        self.rejected_user_id = self.env.uid
        self.reject_date = fields.Date.today()
        
        # Create rejection activity for employee
        self._create_rejection_activity('head')

    def action_purchase_approval(self):
        """Approval from purchase department"""
        for rec in self.requisition_order_ids:
            if not rec.partner_id:
                raise ValidationError('Please select vendor for purchase items')
        self.write({'state': 'approved'})
        self.manager_id = self.env.uid
        self.department_approval_date = fields.Date.today()
        
        # Create approval completion activity
        self._create_approval_completion_activity()

    def action_purchase_cancel(self):
        """Cancellation from purchase department"""
        self.write({'state': 'draft'})
        self.rejected_user_id = self.env.uid
        self.reject_date = fields.Date.today()
        
        # Create rejection activity for employee
        self._create_rejection_activity('purchase')

    def action_cancel_requisition(self):
        """Cancel requisition and return to draft state (only for original requester)"""
        if not self.user_is_requester:
            raise ValidationError('Only the original requester can cancel this requisition.')
        self.write({'state': 'draft'})
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

    @api.depends('requisition_order_ids.price_subtotal')
    def _compute_total_amount(self):
        """Calculate total amount for the requisition"""
        for requisition in self:
            requisition.total_amount = sum(line.price_subtotal for line in requisition.requisition_order_ids)

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
    
    def _create_head_approval_activity(self):
        """Create activity for department head approval"""
        if not self.manager_user_id:
            return
            
        activity_type_id = self.env.ref('employee_purchase_requisition.mail_activity_type_head_approval').id
        date_deadline = self.requisition_deadline or fields.Date.today() + timedelta(days=3)
        
        self.activity_schedule(
            activity_type_id=activity_type_id,
            user_id=self.manager_user_id.id,
            date_deadline=date_deadline,
            summary=f'PR {self.name} - Head Approval Required',
            note=f'Purchase Requisition {self.name} from {self.employee_id.name} requires your approval.\n\n'
                  f'Department: {self.dept_id.name if self.dept_id else "N/A"}\n'
                  f'Total Amount: {self.total_amount:,.2f} {self.company_currency_id.symbol if self.company_currency_id else ""}\n'
                  f'Purpose: {self.purpose or "N/A"}\n\n'
                  f'Please review and approve or reject this requisition.'
        )
    
    def _create_purchase_approval_activity(self):
        """Create activity for purchase department processing"""
        if not self.user_id:
            return
            
        activity_type_id = self.env.ref('employee_purchase_requisition.mail_activity_type_purchase_approval').id
        date_deadline = self.requisition_deadline or fields.Date.today() + timedelta(days=5)
        
        self.activity_schedule(
            activity_type_id=activity_type_id,
            user_id=self.user_id.id,
            date_deadline=date_deadline,
            summary=f'PR {self.name} - Purchase Processing Required',
            note=f'Purchase Requisition {self.name} has been approved by {self.requisition_head_id.name}.\n\n'
                  f'Department: {self.dept_id.name if self.dept_id else "N/A"}\n'
                  f'Total Amount: {self.total_amount:,.2f} {self.company_currency_id.symbol if self.company_currency_id else ""}\n'
                  f'Items: {len(self.requisition_order_ids)}\n\n'
                  f'Please review vendors and process this requisition for purchase order creation.'
        )
    
    def _create_approval_completion_activity(self):
        """Create activity for approval completion"""
        # Notify the original requester that PR is approved
        if not self.create_uid:
            return
            
        activity_type_id = self.env.ref('employee_purchase_requisition.mail_activity_type_pr_approved').id
        date_deadline = fields.Date.today() + timedelta(days=1)
        
        self.activity_schedule(
            activity_type_id=activity_type_id,
            user_id=self.create_uid.id,
            date_deadline=date_deadline,
            summary=f'PR {self.name} - Approved',
            note=f'Purchase Requisition {self.name} has been fully approved!\n\n'
                  f'Department: {self.dept_id.name if self.dept_id else "N/A"}\n'
                  f'Total Amount: {self.total_amount:,.2f} {self.company_currency_id.symbol if self.company_currency_id else ""}\n'
                  f'Approved by: {self.requisition_head_id.name} (Head), {self.manager_id.name} (Purchase)\n\n'
                  f'You can now create purchase orders for this requisition.'
        )
    
    def _create_rejection_activity(self, rejection_type):
        """Create activity for rejection notification"""
        if not self.create_uid:
            return
            
        activity_type_id = self.env.ref('employee_purchase_requisition.mail_activity_type_pr_rejected').id
        date_deadline = fields.Date.today() + timedelta(days=1)
        
        if rejection_type == 'head':
            rejected_by = self.requisition_head_id.name if self.requisition_head_id else 'Department Head'
            reason = 'Department Head'
        else:
            rejected_by = self.manager_id.name if self.manager_id else 'Purchase Department'
            reason = 'Purchase Department'
        
        self.activity_schedule(
            activity_type_id=activity_type_id,
            user_id=self.create_uid.id,
            date_deadline=date_deadline,
            summary=f'PR {self.name} - Rejected',
            note=f'Purchase Requisition {self.name} has been rejected.\n\n'
                  f'Rejected by: {rejected_by} ({reason})\n'
                  f'Department: {self.dept_id.name if self.dept_id else "N/A"}\n'
                  f'Total Amount: {self.total_amount:,.2f} {self.company_currency_id.symbol if self.company_currency_id else ""}\n\n'
                  f'Please review the rejection and make necessary corrections if needed.'
        )

class RequisitionOrder(models.Model):
    _name = 'requisition.order'
    _description = 'Requisition Order Line'

    requisition_product_id = fields.Many2one('employee.purchase.requisition', string="Requisition")
    product_id = fields.Many2one('product.product', string="Product")
    quantity = fields.Float(string="จำนวนขอซื้อ", required=True)
    product_uom_id = fields.Many2one('uom.uom', string="หน่วย")
    price_unit = fields.Float(string="ราคา/หน่วย", default=0.0)
    requisition_order_ids = fields.One2many('requisition.order', 'requisition_id', string="รายการสินค้า")
    need_date = fields.Date(string='วันที่ต้องการสินค้า')
    need_date = fields.Date(string="วันที่ต้องการ")
    partner_id = fields.Many2one('res.partner', string="ผู้จัดจำหน่าย")
    delivery_location_id = fields.Many2one('stock.location', string="สถานที่ส่ง/คลัง")

    def format_date(self, date_obj):
        if date_obj and hasattr(date_obj, 'strftime') and callable(date_obj.strftime):
            return date_obj.strftime('%d/%m/%Y')
        return ''