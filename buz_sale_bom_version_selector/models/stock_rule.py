# -*- coding: utf-8 -*-
from odoo import models, fields, api

class StockRule(models.Model):
    _inherit = 'stock.rule'

    def _prepare_mo_vals(self, product_id, product_qty, product_uom, location_dest_id, name, origin, company_id, values, bom):
        res = super(StockRule, self)._prepare_mo_vals(
            product_id, product_qty, product_uom, location_dest_id, name, origin, company_id, values, bom
        )
        if values.get('bom_id'):
            res['bom_id'] = values['bom_id']
        return res
