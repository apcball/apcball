# Part of Odoo. See COPYRIGHT & LICENSE files for full copyright and licensing details.
from odoo import api, fields, models, _
from odoo.tools import float_is_zero, OrderedSet, float_repr



class StockQuant(models.Model):
    _inherit = 'stock.quant'

    @api.depends('company_id', 'location_id', 'owner_id', 'product_id', 'quantity')
    def _compute_value(self):
        # First call the base method to preserve core Odoo logic
        super()._compute_value()

        for quant in self:
            # Skip if quant has no meaningful quantity or is excluded
            if not quant.location_id or not quant.product_id \
                    or not quant.location_id._should_be_valued() \
                    or quant._should_exclude_for_valuation() \
                    or float_is_zero(quant.quantity, precision_rounding=quant.product_id.uom_id.rounding):
                continue

            # Inject AVCO by Location logic
            if quant.product_id.cost_method == 'avco_by_location':
                standard_price = quant.product_id.with_company(quant.company_id).get_last_cost_history \
                    (location=quant.location_id)
                quant.value = quant.quantity * standard_price


