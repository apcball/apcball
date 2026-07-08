from odoo import api, fields, models, _

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    standard_cost_price = fields.Float(
        string="Standard Cost (Sales)",
        compute='_compute_standard_cost_purchase_price',
        store=True,
        digits='Product Price',
        precompute=True
    )
    
    # Override purchase_price to use standard cost from pricelist
    # This will automatically affect margin calculation in Odoo
    purchase_price = fields.Float(
        compute='_compute_standard_cost_purchase_price',
        store=True,
        readonly=False,
        digits='Product Price'
    )

    @api.depends('product_id', 'company_id', 'currency_id', 'product_uom', 'order_id.date_order', 'order_id.company_id', 'order_id.pricelist_id')
    def _compute_standard_cost_purchase_price(self):
        # Cache pricelists by company so a batch of lines reuses one search,
        # and so POS Lite / SO share the exact same cost-fetching helper.
        pricelists = {}
        Pricelist = self.env['product.pricelist']

        for line in self:
            if not line.product_id or not line.order_id:
                line.standard_cost_price = 0.0
                line.purchase_price = 0.0
                continue

            company = line.company_id or line.order_id.company_id
            cid = company.id
            if cid not in pricelists:
                pricelists[cid] = Pricelist._get_standard_cost_pricelist(company)
            pricelist = pricelists[cid]

            if not pricelist:
                line.standard_cost_price = 0.0
                line.purchase_price = 0.0
                continue

            date_order = line.order_id.date_order or fields.Date.today()
            cost_price = pricelist._get_product_standard_cost_price(
                line.product_id, line.currency_id,
                company=company, date=date_order, uom=line.product_uom,
            )

            line.standard_cost_price = cost_price
            line.purchase_price = cost_price

    @api.onchange('product_id', 'product_uom', 'product_uom_qty')
    def _onchange_product_cost(self):
        """Trigger cost recomputation when product changes"""
        for line in self:
            if line.product_id and line.order_id:
                line._compute_standard_cost_purchase_price()
