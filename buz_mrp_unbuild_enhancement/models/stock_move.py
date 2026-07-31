# Part of buz addons for Mogen Co. See LICENSE file.
from odoo import fields, models
from odoo.tools import float_is_zero


class StockMove(models.Model):
    _inherit = 'stock.move'

    unbuild_component_line_id = fields.Many2one(
        'mrp.unbuild.component.line',
        string='Unbuild Component Line',
        help='Technical link back to the unbuild component line that '
             'generated this move, used to apply its Cost Share (%) when '
             'valuing the move.',
    )

    def _get_price_unit(self):
        line = self.unbuild_component_line_id
        if not line or float_is_zero(line.cost_share, precision_digits=2):
            return super()._get_price_unit()

        unbuild = line.unbuild_id
        finished_move = unbuild.produce_line_ids.filtered(
            lambda m: m.product_id == unbuild.product_id
            and m.state == 'done')
        total_value = abs(sum(
            finished_move.stock_valuation_layer_ids.mapped('value')))
        rounding = self.product_uom.rounding or 0.01
        if float_is_zero(total_value, precision_digits=2) or float_is_zero(
                self.product_uom_qty, precision_rounding=rounding):
            return super()._get_price_unit()

        return (line.cost_share / 100.0 * total_value) / self.product_uom_qty
