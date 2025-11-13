# Part of Odoo. See COPYRIGHT & LICENSE files for full copyright and licensing details.
from odoo import api, fields, models, _


class StockValuationLayer(models.Model):
    """Stock Valuation Layer"""

    _inherit = 'stock.valuation.layer'

    location_id = fields.Many2one('stock.location', string='Location')

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if values.get('stock_valuation_layer_id') and 'location_id' not in values or not values.get('location_id'):
                linked_valuation = self.env['stock.valuation.layer'].browse(values.get('stock_valuation_layer_id'))
                if linked_valuation:
                    values['location_id'] = linked_valuation.location_id.id if linked_valuation.location_id else False
        return super(StockValuationLayer, self).create(vals_list)

