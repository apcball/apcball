from odoo import models, fields, api

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    include_installation = fields.Boolean(
        string='Include Installation',
        default=False
    )

    installation_price = fields.Float(
        string='Installation Price',
        compute='_compute_installation_price',
        store=True,
        readonly=True
    )

    @api.depends('product_id', 'order_id.pricelist_id', 'product_uom_qty', 'order_id.date_order')
    def _compute_installation_price(self):
        for line in self:
            if not line.product_id or not line.order_id.pricelist_id:
                line.installation_price = 0.0
                continue
            
            pricelist = line.order_id.pricelist_id
            product = line.product_id
            qty = line.product_uom_qty or 1.0
            date = line.order_id.date_order
            
            # _get_product_price_rule returns (price, rule_id)
            rule = pricelist._get_product_price_rule(
                product, quantity=qty, date=date
            )
            
            rule_id = rule[1]
            if rule_id:
                item = self.env['product.pricelist.item'].browse(rule_id)
                line.installation_price = item.installation_price
            else:
                line.installation_price = 0.0

    @api.onchange('include_installation')
    def _onchange_include_installation_toggle(self):
        if not self.product_id or not self.order_id.pricelist_id:
            return
            
        # Only handle the "Uncheck" event here to revert to pricelist price.
        # When "Checking", the guard method will handle setting the price.
        if not self.include_installation:
             pricelist_price = self.order_id.pricelist_id._get_product_price(
                 self.product_id, self.product_uom_qty or 1.0, 
                 date=self.order_id.date_order
             )
             self.price_unit = pricelist_price

    @api.onchange('include_installation', 'installation_price', 'product_uom_qty', 'product_id', 'price_unit')
    def _onchange_maintain_installation_price(self):
        if not self.product_id or not self.order_id.pricelist_id:
            return

        # If installation is included, we MUST enforce Price = Base + Install
        # This acts as a watchdog against standard Odoo resets (like Qty change)
        if self.include_installation:
             pricelist_price = self.order_id.pricelist_id._get_product_price(
                 self.product_id, self.product_uom_qty or 1.0, 
                 date=self.order_id.date_order
             )
             expected_price = pricelist_price + self.installation_price
             
             if abs(self.price_unit - expected_price) > 0.001:
                 self.price_unit = expected_price

    # We should also ensure that if installation_price changes (e.g. qty change changes rule), price_unit updates if included.
    @api.depends('installation_price', 'include_installation')
    def _compute_price_unit_installation(self):
        # We can't easily use Depends for price_unit because it's editable. 
        # But we can use onchange or override write/create?
        # Odoo's price_unit isn't always computed.
        pass
