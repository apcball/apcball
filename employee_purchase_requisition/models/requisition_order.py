from odoo import api, fields, models

class RequisitionOrder(models.Model):
    _name = 'requisition.order'
    _description = 'Requisition Order'

    requisition_product_id = fields.Many2one(  # ใช้ชื่อเดียวกับที่อ้างอิงใน One2many
        'employee.purchase.requisition',
        string='Requisition Reference',
        ondelete='cascade'
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True
    )
    description = fields.Text(string='Description')
    quantity = fields.Float(string='Quantity', default=1.0)
    uom = fields.Many2one(
        'uom.uom',
        string='Unit of Measure'
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Vendor'
    )
    analytic_distribution = fields.Json(
        string="Analytic Distribution",
        copy=True,
        store=True,
        default={}
    )
    analytic_precision = fields.Integer(
        string="Analytic Precision",
        default=lambda self: self.env['decimal.precision'].precision_get('Percentage Analytic')
    )
    
    unit_price = fields.Float(
        string="Unit Price",
        help="Enter the custom unit price for this product"
    )
    price_subtotal = fields.Float(
        string="Subtotal",
        compute="_compute_price_subtotal",
        store=True,
        help="Automatically calculated as quantity × unit price"
    )

    @api.depends('quantity', 'unit_price')
    def _compute_price_subtotal(self):
        """Calculate subtotal for each line item"""
        for line in self:
            line.price_subtotal = line.quantity * line.unit_price

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.description = self.product_id.name
            self.uom = self.product_id.uom_id.id