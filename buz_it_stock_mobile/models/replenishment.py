from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare


class PurchaseRequisition(models.Model):
    _inherit = 'employee.purchase.requisition'

    it_config_id = fields.Many2one(
        'buz.it.config', string='คลัง IT ที่ขอเติม', check_company=True,
        copy=False, index=True, ondelete='restrict',
    )
    it_purchase_ids = fields.One2many('purchase.order', 'it_requisition_id', string='ใบสั่งซื้อ IT')
    it_product_ids = fields.Many2many('product.product', compute='_compute_it_products', string='สินค้าที่ขอซื้อ')

    @api.depends('requisition_order_ids.product_id')
    def _compute_it_products(self):
        for requisition in self:
            requisition.it_product_ids = requisition.requisition_order_ids.product_id

    @api.constrains('it_config_id', 'company_id')
    def _check_it_company(self):
        for requisition in self:
            if requisition.it_config_id and requisition.it_config_id.company_id != requisition.company_id:
                raise ValidationError(_('The IT warehouse must belong to the requisition company.'))

    def action_create_purchase_order(self):
        self.ensure_one()
        if self.it_config_id:
            # Keep the relational link when the standard workflow splits POs by vendor.
            return super(PurchaseRequisition, self.with_context(
                default_it_requisition_id=self.id,
            )).action_create_purchase_order()
        return super().action_create_purchase_order()

    def _it_pending_product_ids(self):
        self.ensure_one()
        if self.state in ('received', 'cancelled'):
            return set()
        if not self.it_purchase_ids:
            return set(self.requisition_order_ids.filtered(lambda line: line.quantity > 0).product_id.ids)
        pending = set()
        for order in self.it_purchase_ids.filtered(lambda po: po.state != 'cancel'):
            for line in order.order_line.filtered(lambda line: not line.display_type):
                if float_compare(line.product_qty, line.qty_received,
                                 precision_rounding=line.product_uom.rounding) > 0:
                    pending.add(line.product_id.id)
        return pending


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    it_requisition_id = fields.Many2one(
        'employee.purchase.requisition', string='IT Purchase Requisition',
        check_company=True, copy=False, index=True, ondelete='restrict',
    )

    @api.constrains('it_requisition_id', 'company_id')
    def _check_it_requisition_company(self):
        for order in self:
            if order.it_requisition_id and order.it_requisition_id.company_id != order.company_id:
                raise ValidationError(_('The IT requisition must belong to the purchase order company.'))
