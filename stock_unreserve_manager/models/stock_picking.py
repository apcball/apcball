from odoo import models, fields, api, _
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    # -------------------------------------------------------------------------
    # Computed helpers
    # -------------------------------------------------------------------------
    unreserve_log_count = fields.Integer(
        string='Unreserve Logs',
        compute='_compute_unreserve_log_count',
    )

    @api.depends('name')
    def _compute_unreserve_log_count(self):
        for picking in self:
            picking.unreserve_log_count = self.env['stock.unreserve.log'].search_count(
                [('picking_id', '=', picking.id)]
            )

    # -------------------------------------------------------------------------
    # Action – standard unreserve (assigned / partially_available only)
    # -------------------------------------------------------------------------
    def action_unreserve_picking(self):
        """Unreserve a picking that is in 'assigned' or 'partially_available' state."""
        for picking in self:
            if picking.state not in ('assigned', 'partially_available'):
                raise UserError(
                    _(
                        "Transfer '%(name)s' cannot be unreserved: it is in state '%(state)s'.\n"
                        "Only transfers in 'Ready' or 'Partially Available' can be unreserved.",
                        name=picking.name,
                        state=picking.state,
                    )
                )
            self._do_unreserve_and_log(picking, unreserve_type='picking')
        return True

    # -------------------------------------------------------------------------
    # Action – force unreserve (manager-only, any ready/partial state)
    # -------------------------------------------------------------------------
    def action_force_unreserve(self):
        """Force-unreserve: reset move states to 'confirmed', bypass downstream conflicts."""
        self._check_unreserve_manager()
        for picking in self:
            if picking.state not in ('assigned', 'partially_available', 'waiting'):
                raise UserError(
                    _(
                        "Transfer '%(name)s' (state: %(state)s) cannot be force-unreserved.",
                        name=picking.name,
                        state=picking.state,
                    )
                )
            self._do_unreserve_and_log(picking, unreserve_type='force', force=True)
        return True

    # -------------------------------------------------------------------------
    # Smart button – open log list
    # -------------------------------------------------------------------------
    def action_view_unreserve_logs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Unreserve Logs'),
            'res_model': 'stock.unreserve.log',
            'view_mode': 'tree,form',
            'domain': [('picking_id', '=', self.id)],
            'context': {'default_picking_id': self.id},
        }

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------
    def _do_unreserve_and_log(self, picking, unreserve_type='picking', force=False):
        """Core unreserve logic with integrity checks and audit logging."""
        # Collect qty per product before unreserving for log accuracy
        product_qtys = {}
        for move in picking.move_ids.filtered(lambda m: m.state not in ('done', 'cancel')):
            reserved = sum(move.move_line_ids.mapped('quantity'))
            if reserved:
                product_qtys[move.product_id] = product_qtys.get(move.product_id, 0.0) + reserved

        # Perform the actual unreserve via Odoo's standard method
        picking.move_ids._do_unreserve()

        if force:
            # Reset move state to 'confirmed' to clear downstream waiting dependencies
            moves_to_reset = picking.move_ids.filtered(
                lambda m: m.state not in ('done', 'cancel')
            )
            moves_to_reset.write({'state': 'confirmed'})

        # Write audit logs
        log_vals = []
        for product, qty in product_qtys.items():
            log_vals.append({
                'user_id': self.env.uid,
                'picking_id': picking.id,
                'product_id': product.id,
                'qty': qty,
                'type': unreserve_type,
                'reason': 'Force unreserve' if force else 'Standard unreserve',
            })
        if log_vals:
            self.env['stock.unreserve.log'].create(log_vals)
        elif not product_qtys:
            # Still log even if nothing was reserved – for audit trail
            self.env['stock.unreserve.log'].create({
                'user_id': self.env.uid,
                'picking_id': picking.id,
                'qty': 0.0,
                'type': unreserve_type,
                'reason': 'No reserved qty found',
            })

    def _check_unreserve_manager(self):
        """Raise if the current user does not belong to the unreserve manager group."""
        if not self.env.user.has_group(
            'stock_unreserve_manager.group_unreserve_manager'
        ):
            raise UserError(
                _("You do not have the 'Unreserve Manager' security right to perform this action.")
            )
