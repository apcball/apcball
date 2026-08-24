from odoo import _, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _check_demand_qty(self):
        for picking in self:
            bad_moves = picking.move_ids.filtered(
                lambda m: m.state != 'cancel' and m.product_uom_qty <= 0
            )
            if bad_moves:
                raise UserError(_(
                    "ต้องใส่ Demand (%(picking)s): %(products)s",
                    picking=picking.name,
                    products=', '.join(bad_moves.mapped('product_id.display_name')),
                ))

    def action_confirm(self):
        self._check_demand_qty()
        return super().action_confirm()

    def button_validate(self):
        self._check_demand_qty()
        return super().button_validate()
