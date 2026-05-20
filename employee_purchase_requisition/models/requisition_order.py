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
    picking_type_id = fields.Many2one(
        'stock.picking.type',
        string='Picking Type',
        domain="[('code', '=', 'incoming')]",
        help='Select the picking type for receiving goods'
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

    # ── Purchase History ─────────────────────────────────────────
    last_purchase_price = fields.Float(
        string="Last Purchase Price",
        compute="_compute_last_purchase_info",
        help="Last purchase price unit from confirmed purchase orders"
    )
    last_purchase_date = fields.Date(
        string="Last Purchase Date",
        compute="_compute_last_purchase_info",
        help="Date of the last purchase order for this product"
    )

    @api.depends('quantity', 'unit_price')
    def _compute_price_subtotal(self):
        """Calculate subtotal for each line item"""
        for line in self:
            line.price_subtotal = line.quantity * line.unit_price

    @api.depends('product_id')
    def _compute_last_purchase_info(self):
        """Fetch last purchase price and date from confirmed purchase order lines."""
        for line in self:
            line.last_purchase_price = 0.0
            line.last_purchase_date = False
            if not line.product_id:
                continue
            # Search purchase.order ordered by date, then get the matching line
            last_order = self.env['purchase.order'].search([
                ('order_line.product_id', '=', line.product_id.id),
                ('state', 'in', ('purchase', 'done')),
            ], order='date_order desc, id desc', limit=1)
            if last_order:
                last_line = last_order.order_line.filtered(
                    lambda l: l.product_id == line.product_id
                )[:1]
                if last_line:
                    line.last_purchase_price = last_line.price_unit
                    line.last_purchase_date = last_order.date_order

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.description = self.product_id.name
            self.uom = self.product_id.uom_id.id
            self._compute_last_purchase_info()