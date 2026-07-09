from odoo import _, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _reserve_manager_reserved_qty(self):
        self.ensure_one()
        return sum(self.move_line_ids.mapped('quantity'))

    def _reserve_manager_reserve_state(self):
        self.ensure_one()
        reserved_qty = self._reserve_manager_reserved_qty()
        if not reserved_qty:
            return 'none'
        if float_compare(
            reserved_qty,
            self.product_uom_qty,
            precision_rounding=self.product_uom.rounding,
        ) >= 0:
            return 'full'
        return 'partial'

    def _reserve_manager_available_qty(self):
        self.ensure_one()
        return self.env['stock.quant']._get_available_quantity(
            self.product_id,
            self.location_id,
        )

    def _reserve_manager_snapshot(self):
        self.ensure_one()
        return {
            'reserved_qty': self._reserve_manager_reserved_qty(),
            'available_qty': self._reserve_manager_available_qty(),
            'move_state': self.state,
            'reserve_state': self._reserve_manager_reserve_state(),
        }

    def action_reserve_for_manager(self):
        self.ensure_one()
        if self.state in ('done', 'cancel'):
            raise UserError(_("Cannot reserve a move that is already done or cancelled."))
        before_reserved = self._reserve_manager_reserved_qty()
        self._action_assign()
        return before_reserved, self._reserve_manager_reserved_qty()
    def action_unreserve_for_manager(self, unreserve_type='picking', reason=None):
        self.ensure_one()
        if self.state in ('done', 'cancel'):
            raise UserError(_("Cannot unreserve a move that is already done or cancelled."))

        reserved_per_product = {}
        for move_line in self.move_line_ids:
            qty = move_line.quantity or 0.0
            if qty:
                reserved_per_product[move_line.product_id.id] = (
                    reserved_per_product.get(move_line.product_id.id, 0.0) + qty
                )

        before_reserved = self._reserve_manager_reserved_qty()
        self._do_unreserve()

        log_model = self.env.registry.models.get('stock.unreserve.log')
        if log_model:
            log_vals = []
            log_reason = reason or _('Reserve Manager')
            for product_id, qty in reserved_per_product.items():
                log_vals.append({
                    'user_id': self.env.uid,
                    'picking_id': self.picking_id.id if self.picking_id else False,
                    'product_id': product_id,
                    'qty': qty,
                    'type': unreserve_type,
                    'reason': log_reason,
                })
            if not log_vals:
                log_vals.append({
                    'user_id': self.env.uid,
                    'picking_id': self.picking_id.id if self.picking_id else False,
                    'product_id': self.product_id.id,
                    'qty': 0.0,
                    'type': unreserve_type,
                    'reason': reason or _('Reserve Manager'),
                })
            self.env['stock.unreserve.log'].sudo().create(log_vals)

        return before_reserved, self._reserve_manager_reserved_qty()
