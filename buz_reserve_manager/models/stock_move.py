from odoo import models, fields, api, _
from odoo.exceptions import UserError


class StockMove(models.Model):
    _inherit = 'stock.move'

    # -------------------------------------------------------------------------
    # Helper – manual reserve on a specific stock.move
    # -------------------------------------------------------------------------
    def action_manual_reserve(self, reserve_qty=None):
        """
        Manually reserve a specific quantity for this move.
        If reserve_qty is None, reserve the full demand (product_uom_qty).
        Works by creating/updating stock.move.line records.
        """
        self.ensure_one()
        if self.state in ('done', 'cancel'):
            raise UserError(_("Cannot reserve a move that is already done or cancelled."))

        already_reserved = sum(self.move_line_ids.mapped('quantity'))
        remaining_demand = self.product_uom_qty - already_reserved

        if remaining_demand <= 0:
            raise UserError(_("No quantity to reserve (already fully reserved)."))

        qty = reserve_qty if reserve_qty is not None else remaining_demand
        qty = min(qty, remaining_demand)

        if qty <= 0:
            raise UserError(_("No quantity to reserve (already fully reserved)."))

        available_qty = self._get_available_qty()
        reserve_qty = min(qty, available_qty)

        if reserve_qty <= 0:
            raise UserError(_("No stock available to reserve for product '%s'.") % self.product_id.display_name)

        # Create a stock.move.line to represent the manual reservation
        # Try to find an existing SML for this move
        existing_sml = self.move_line_ids.filtered(
            lambda l: l.location_id == self.location_id
            and l.location_dest_id == self.location_dest_id
            and not l.lot_id
        )[:1]

        if existing_sml:
            existing_sml.write({
                'quantity': existing_sml.quantity + reserve_qty,
                'product_uom_id': self.product_uom.id,
            })
        else:
            self.env['stock.move.line'].create({
                'move_id': self.id,
                'product_id': self.product_id.id,
                'product_uom_id': self.product_uom.id,
                'quantity': reserve_qty,
                'location_id': self.location_id.id,
                'location_dest_id': self.location_dest_id.id,
                'picking_id': self.picking_id.id,
                'state': 'assigned',
            })

        # Recompute move state
        self._recompute_state()

        return reserve_qty

    def action_unreserve_single(self):
        """
        Unreserve this specific stock move entirely.
        """
        self.ensure_one()
        if self.state not in ('assigned', 'partially_available'):
            raise UserError(
                _("Move '%s' cannot be unreserved: state is '%s'.")
                % (self.display_name, self.state)
            )

        # Snapshot reserved qty before unreserving
        reserved_qtys = {}
        for ml in self.move_line_ids:
            qty = ml.quantity
            if qty:
                reserved_qtys[ml.product_id] = reserved_qtys.get(ml.product_id, 0.0) + qty

        # Call Odoo standard unreserve
        self._do_unreserve()

        # Write audit log (reuse stock.unreserve.log if available, else create our own)
        self._log_unreserve(reserved_qtys, 'manual')

        return True

    def _get_available_qty(self):
        """Get available stock quantity for this product/location."""
        self.ensure_one()
        return self.env['stock.quant']._get_available_quantity(
            self.product_id,
            self.location_id,
        )

    def _log_unreserve(self, product_qtys, unreserve_type='manual'):
        """Write unreserve audit log."""
        log_model = self.env.get('stock.unreserve.log')
        if not log_model:
            return

        log_vals = []
        for product, qty in product_qtys.items():
            log_vals.append({
                'user_id': self.env.uid,
                'picking_id': self.picking_id.id if self.picking_id else False,
                'product_id': product.id,
                'qty': qty,
                'type': unreserve_type,
                'reason': 'Reserve Manager - Single Unreserve',
            })

        if not log_vals:
            log_vals.append({
                'user_id': self.env.uid,
                'picking_id': self.picking_id.id if self.picking_id else False,
                'product_id': self.product_id.id,
                'qty': 0.0,
                'type': unreserve_type,
                'reason': 'No reserved qty found (Reserve Manager)',
            })

        log_model.create(log_vals)