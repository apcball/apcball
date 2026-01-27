# -*- coding: utf-8 -*-
from odoo import api, fields, models

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    is_retail_installation = fields.Boolean(
        related='pricelist_id.is_retail_installation',
        store=True,
        readonly=True
    )
    is_project_installation = fields.Boolean(
        related='pricelist_id.is_project_installation',
        store=True,
        readonly=True
    )

    @api.onchange('pricelist_id')
    def _onchange_pricelist_installation(self):
        if self.state != 'draft':
            return
        if self.order_line:
            for line in self.order_line:
                line._compute_price_unit()

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    include_installation = fields.Boolean(
        string='Include Installation',
        default=False
    )
    
    installation_cost_amount = fields.Monetary(
        string='Installation Cost',
        compute='_compute_installation_cost_amount',
        store=True,
        currency_field='currency_id'
    )

    @api.depends('product_id', 'order_id.is_retail_installation', 'order_id.is_project_installation', 'include_installation')
    def _compute_installation_cost_amount(self):
        """Compute installation cost amount"""
        for line in self:
            line.installation_cost_amount = line._get_installation_cost() if line.include_installation else 0.0

    def _get_installation_cost(self):
        """Get installation cost based on pricelist type"""
        self.ensure_one()

        product = self.product_id
        order = self.order_id

        if not product or not order:
            return 0.0

        # If both are enabled, prioritize project installation
        if order.is_project_installation:
            return product.installation_cost_project or 0.0
        elif order.is_retail_installation:
            return product.installation_cost_retail or 0.0

        return 0.0

    @api.depends('product_id', 'product_uom', 'product_uom_qty', 'include_installation', 'installation_cost_amount')
    def _compute_price_unit(self):
        """Override to add installation cost AFTER pricelist calculation"""
        # First, let the standard pricelist calculation happen
        res = super(SaleOrderLine, self)._compute_price_unit()
        
        # Then add installation cost if needed
        for line in self:
            if line.include_installation and line.product_id and line.installation_cost_amount:
                # Add installation cost to the price after pricelist calculation
                line.price_unit += line.installation_cost_amount
        
        return res

    @api.onchange('include_installation')
    def _onchange_include_installation(self):
        """Recalculate price when installation checkbox changes"""
        if self.product_id:
            self._compute_price_unit()
    
    @api.depends('product_uom_qty', 'discount', 'price_unit', 'tax_id', 'installation_cost_amount')
    def _compute_margin(self):
        """Override margin calculation to exclude installation cost from margin"""
        for line in self:
            # Get the base price unit without installation
            base_price_unit = line.price_unit - (line.installation_cost_amount if line.include_installation else 0.0)
            
            # Calculate margin based on base price only
            price = base_price_unit * (1 - (line.discount or 0.0) / 100.0)
            quantity = line.product_uom_qty
            
            # Standard margin calculation on base price
            line.margin = (price * quantity) - (line.purchase_price * quantity)
            line.margin_percent = line.margin / (price * quantity) * 100 if (price * quantity) else 0
