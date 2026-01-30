# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.tools import float_is_zero


class StockMove(models.Model):
    _inherit = 'stock.move'
    
    # Field for manual cost price on receipt
    custom_cost_price = fields.Float(
        string='Cost Price',
        digits='Product Price',
        copy=False,
        help='ราคาต้นทุนที่กำหนดเอง ใช้สำหรับการรับสินค้าและ Inventory Valuation',
    )
    
    use_custom_cost = fields.Boolean(
        string='Use Custom Cost',
        default=False,
        copy=False,
        help='เมื่อเปิดใช้งาน จะใช้ราคาต้นทุนที่กำหนดเองแทนราคาจาก Product',
    )
    
    is_from_purchase = fields.Boolean(
        string='From Purchase',
        compute='_compute_is_from_purchase',
        store=True,
        help='ระบุว่า move นี้มาจาก Purchase Order หรือไม่',
    )
    
    @api.depends('purchase_line_id')
    def _compute_is_from_purchase(self):
        """Compute if this move is from a purchase order"""
        for move in self:
            move.is_from_purchase = bool(move.purchase_line_id)
    
    def _get_default_cost_price(self):
        """Get default cost price from PO line or product standard price"""
        self.ensure_one()
        company = self.company_id or self.env.company
        
        # If from Purchase Order, use PO line price
        if hasattr(self, 'purchase_line_id') and self.purchase_line_id:
            po_line = self.purchase_line_id
            # Convert PO price to company currency if needed
            if po_line.currency_id != company.currency_id:
                price = po_line.currency_id._convert(
                    po_line.price_unit,
                    company.currency_id,
                    company,
                    po_line.order_id.date_order or fields.Date.today(),
                )
            else:
                price = po_line.price_unit
            return price
        
        # Otherwise use product standard price
        product = self.product_id.with_company(company)
        return product.standard_price
    
    @api.onchange('product_id')
    def _onchange_product_id_set_custom_cost(self):
        """Set default custom cost from PO or product's standard price"""
        if self.product_id:
            self.custom_cost_price = self._get_default_cost_price()
            self.use_custom_cost = True
    
    @api.onchange('custom_cost_price')
    def _onchange_custom_cost_price(self):
        """Auto enable use_custom_cost when cost is manually entered"""
        if self.custom_cost_price > 0:
            self.use_custom_cost = True
    
    @api.model_create_multi
    def create(self, vals_list):
        """Set default custom cost from PO or product's standard price when creating"""
        records = super(StockMove, self).create(vals_list)
        
        # Set custom cost for newly created records that don't have it set
        for record in records:
            if record.product_id and not record.custom_cost_price:
                record.custom_cost_price = record._get_default_cost_price()
                record.use_custom_cost = True
        
        return records
    
    def _is_in(self):
        """Check if this is an incoming move (receipt)"""
        self.ensure_one()
        return self.location_dest_id._should_be_valued() and \
               not self.location_id._should_be_valued()
    
    def _get_price_unit(self):
        """Override to use custom cost price if set for incoming moves"""
        self.ensure_one()
        
        # Only use custom cost for incoming moves with custom cost enabled
        if self._is_in() and self.use_custom_cost and self.custom_cost_price > 0:
            return self.custom_cost_price
        
        return super(StockMove, self)._get_price_unit()
    
    def _get_in_svl_vals(self, forced_quantity):
        """Override to use custom cost price for incoming stock valuation"""
        svl_vals_list = []
        for move in self:
            move = move.with_company(move.company_id)
            valued_move_lines = move._get_in_move_lines()
            valued_quantity = sum(valued_move_lines.mapped("quantity_product_uom"))
            
            if float_is_zero(forced_quantity or valued_quantity, 
                           precision_rounding=move.product_id.uom_id.rounding):
                continue
            
            # Use custom cost if enabled, otherwise use standard logic
            if move.use_custom_cost and move.custom_cost_price > 0:
                unit_cost = move.custom_cost_price
            elif move.product_id.cost_method != 'standard':
                unit_cost = abs(move._get_price_unit())
            else:
                unit_cost = move.product_id.standard_price
            
            svl_vals = move.product_id._prepare_in_svl_vals(
                forced_quantity or valued_quantity, unit_cost
            )
            svl_vals.update(move._prepare_common_svl_vals())
            
            if forced_quantity:
                svl_vals['description'] = 'Correction of %s (modification of past move)' % (
                    move.picking_id.name or move.name
                )
            svl_vals_list.append(svl_vals)
        
        return svl_vals_list
