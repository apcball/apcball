# Part of Odoo. See COPYRIGHT & LICENSE files for full copyright and licensing details.
from odoo import _, fields, models


class StockRule(models.Model):
    _inherit = 'stock.rule'

    def _get_stock_move_values(self, product_id, product_qty, product_uom,
                               location_dest_id, name, origin, company_id, values):
        """
        inherit to add src location
        """
        vals = super(StockRule, self)._get_stock_move_values(
            product_id, product_qty, product_uom, location_dest_id, name, origin,
            company_id, values)
        location_dest = False
        if vals.get('location_final_id'):
            location_dest = self.env['stock.location'].browse(vals.get('location_final_id'))
        if values.get('sale_line_id', False) and location_dest \
                and location_dest.usage == 'customer':
            sale_line_id = self.env['sale.order.line'].sudo().browse(
                values['sale_line_id'])
            if sale_line_id.order_id.picking_type_id:
                vals['picking_type_id'] = sale_line_id.order_id.picking_type_id.id
                vals['location_id'] = \
                    sale_line_id.order_id.picking_type_id.default_location_src_id.id

        return vals
