# -*- coding: utf-8 -*-
from odoo import models, fields, api

class StockMove(models.Model):
    _inherit = 'stock.move'

    def _explode_bom(self):
        """
        Override to use the effective BOM from the Sale Order Line if available.
        """
        if self.sale_line_id:
            effective_bom = self.sale_line_id.bom_id or self.sale_line_id.order_id.bom_version_id
            if effective_bom:
                return super(StockMove, self.with_context(force_bom_id=effective_bom.id))._explode_bom()
        return super(StockMove, self)._explode_bom()

    def _prepare_phantom_move_values(self, bom_line, product_qty, quantity_done):
        """
        Ensure we pass down the sale_line_id so subsequent explosions can also use it.
        """
        res = super(StockMove, self)._prepare_phantom_move_values(bom_line, product_qty, quantity_done)
        if self.sale_line_id:
            res['sale_line_id'] = self.sale_line_id.id
        return res

class MrpBom(models.Model):
    _inherit = 'mrp.bom'

    def _bom_find(self, products, picking_type=None, company_id=False, bom_type=False):
        """
        Override _bom_find to check context for a forced bom_id.
        """
        if self.env.context.get('force_bom_id'):
            forced_bom = self.browse(self.env.context.get('force_bom_id'))
            if forced_bom.exists():
                return forced_bom
        return super(MrpBom, self)._bom_find(
            products, picking_type=picking_type, company_id=company_id, bom_type=bom_type
        )
