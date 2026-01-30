# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'
    
    # Related field from stock.move for display in views
    custom_cost_price = fields.Float(
        related='move_id.custom_cost_price',
        string='Cost Price',
        readonly=False,
        digits='Product Price',
        help='ราคาต้นทุนที่กำหนดเอง',
    )
    
    use_custom_cost = fields.Boolean(
        related='move_id.use_custom_cost',
        string='Use Custom Cost',
        readonly=False,
        help='เมื่อเปิดใช้งาน จะใช้ราคาต้นทุนที่กำหนดเอง',
    )
    
    @api.onchange('product_id')
    def _onchange_product_id_set_cost(self):
        """Set default cost from product when product changes (company-specific)"""
        if self.product_id and self.move_id:
            # Get cost price with proper company context
            company = self.move_id.company_id or self.company_id or self.env.company
            product = self.product_id.with_company(company)
            self.move_id.custom_cost_price = product.standard_price
