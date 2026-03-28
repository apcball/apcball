from odoo import models, fields, api, _
from odoo.exceptions import UserError


class StockUnreserveWizard(models.TransientModel):
    _name = 'stock.unreserve.wizard'
    _description = 'Bulk Stock Unreserve Wizard'

    unreserve_type = fields.Selection(
        selection=[
            ('picking', 'By Transfer(s)'),
            ('product', 'By Product(s)'),
            ('all', 'All Reserved Transfers'),
        ],
        string='Unreserve Scope',
        required=True,
        default='picking',
    )
    picking_ids = fields.Many2many(
        'stock.picking',
        string='Transfers',
        domain=[('state', 'in', ('assigned', 'partially_available'))],
    )
    product_ids = fields.Many2many(
        'product.product',
        string='Products',
    )
    location_id = fields.Many2one(
        'stock.location',
        string='From Location (optional)',
        domain=[('usage', 'in', ('internal', 'transit'))],
    )
    force = fields.Boolean(
        string='Force Unreserve',
        help="Reset move state to 'confirmed' after unreserving, clearing downstream waiting dependencies.",
    )
    reason = fields.Char(
        string='Reason',
        help='Optional reason recorded in the audit log.',
    )

    # -------------------------------------------------------------------------
    # Onchange – clear irrelevant fields when scope changes
    # -------------------------------------------------------------------------
    @api.onchange('unreserve_type')
    def _onchange_unreserve_type(self):
        if self.unreserve_type != 'picking':
            self.picking_ids = [(5, 0, 0)]
        if self.unreserve_type != 'product':
            self.product_ids = [(5, 0, 0)]

    # -------------------------------------------------------------------------
    # Main entry point
    # -------------------------------------------------------------------------
    def execute_unreserve(self):
        self._check_unreserve_manager()
        pickings = self._resolve_pickings()
        if not pickings:
            raise UserError(_("No transfers matched your criteria. Nothing to unreserve."))

        unreserve_type_map = {
            'picking': 'bulk_picking',
            'product': 'bulk_product',
            'all': 'bulk_all',
        }
        log_type = unreserve_type_map.get(self.unreserve_type, 'bulk_all')
        reason = self.reason or 'Bulk unreserve'

        log_vals = []
        for picking in pickings:
            # Snapshot reserved qty per product before unreserving
            product_qtys = {}
            for move in picking.move_ids.filtered(
                lambda m: m.state not in ('done', 'cancel')
            ):
                # Optionally filter by product scope
                if (
                    self.unreserve_type == 'product'
                    and self.product_ids
                    and move.product_id not in self.product_ids
                ):
                    continue
                reserved = sum(move.move_line_ids.mapped('quantity'))
                if reserved:
                    product_qtys[move.product_id] = (
                        product_qtys.get(move.product_id, 0.0) + reserved
                    )

            # Unreserve relevant moves
            moves_to_unreserve = picking.move_ids.filtered(
                lambda m: m.state not in ('done', 'cancel')
            )
            if self.unreserve_type == 'product' and self.product_ids:
                moves_to_unreserve = moves_to_unreserve.filtered(
                    lambda m: m.product_id in self.product_ids
                )
            if moves_to_unreserve:
                moves_to_unreserve._do_unreserve()

                if self.force:
                    moves_to_unreserve.filtered(
                        lambda m: m.state not in ('done', 'cancel')
                    ).write({'state': 'confirmed'})

            # Build log entries
            for product, qty in product_qtys.items():
                log_vals.append({
                    'user_id': self.env.uid,
                    'picking_id': picking.id,
                    'product_id': product.id,
                    'qty': qty,
                    'type': log_type,
                    'reason': reason,
                })

        if log_vals:
            self.env['stock.unreserve.log'].create(log_vals)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Unreserve Complete'),
                'message': _(
                    '%(count)d transfer(s) were unreserved successfully.',
                    count=len(pickings),
                ),
                'type': 'success',
                'sticky': False,
            },
        }

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------
    def _resolve_pickings(self):
        """Return the set of pickings to unreserve based on wizard settings."""
        domain = [('state', 'in', ('assigned', 'partially_available'))]
        if self.unreserve_type == 'picking':
            if not self.picking_ids:
                raise UserError(_("Please select at least one transfer."))
            return self.picking_ids.filtered(
                lambda p: p.state in ('assigned', 'partially_available')
            )
        elif self.unreserve_type == 'product':
            if not self.product_ids:
                raise UserError(_("Please select at least one product."))
            move_domain = [
                ('state', 'not in', ('done', 'cancel')),
                ('picking_id.state', 'in', ('assigned', 'partially_available')),
                ('product_id', 'in', self.product_ids.ids),
            ]
            if self.location_id:
                move_domain.append(('location_id', 'child_of', self.location_id.id))
            moves = self.env['stock.move'].search(move_domain)
            return moves.mapped('picking_id')
        else:  # 'all'
            if self.location_id:
                domain.append(('location_id', 'child_of', self.location_id.id))
            return self.env['stock.picking'].search(domain)

    def _check_unreserve_manager(self):
        if not self.env.user.has_group(
            'stock_unreserve_manager.group_unreserve_manager'
        ):
            raise UserError(
                _("You do not have the 'Unreserve Manager' security right to use this wizard.")
            )
