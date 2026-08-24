# Part of buz addons for Mogen Co. See LICENSE file.
from odoo import api, fields, models
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
    unbuild_cost_share = fields.Float(
        string='Cost Share (%)',
        related='unbuild_component_line_id.cost_share',
    )
    unbuild_valuation_value = fields.Float(
        string='Valuation Value',
        compute='_compute_unbuild_valuation',
        help='Actual value posted for this move (sum of its stock '
             'valuation layers), e.g. the FIFO cost consumed or the '
             'Cost Share (%) value allocated to a returned component.',
    )
    unbuild_unit_cost = fields.Float(
        string='Unit Cost',
        compute='_compute_unbuild_valuation',
        help='Valuation Value divided by the quantity moved.',
    )
    unbuild_move_role = fields.Selection(
        [('consume', 'Consumed (Finished Good)'),
         ('component', 'Returned Components'),
         ('scrap', 'Scrap')],
        string='Type',
        compute='_compute_unbuild_move_role',
        store=True,
        help='Groups this move for the Unbuild Overview: the finished '
             'product consumed back into stock, a returned component, '
             'or a scrap-out move.',
    )

    @api.depends('stock_valuation_layer_ids.value',
                 'stock_valuation_layer_ids.quantity', 'product_uom_qty')
    def _compute_unbuild_valuation(self):
        for move in self:
            value = sum(move.stock_valuation_layer_ids.mapped('value'))
            move.unbuild_valuation_value = abs(value)
            move.unbuild_unit_cost = (
                abs(value) / move.product_uom_qty
                if move.product_uom_qty else 0.0)

    @api.depends('scrap_id', 'unbuild_id', 'unbuild_id.product_id',
                 'product_id')
    def _compute_unbuild_move_role(self):
        for move in self:
            if move.scrap_id:
                move.unbuild_move_role = 'scrap'
            elif move.unbuild_id and move.product_id == \
                    move.unbuild_id.product_id:
                move.unbuild_move_role = 'consume'
            elif move.unbuild_id:
                move.unbuild_move_role = 'component'
            else:
                move.unbuild_move_role = False

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
