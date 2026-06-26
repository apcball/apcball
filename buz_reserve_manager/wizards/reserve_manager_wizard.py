from odoo import models, fields, api, _


class BuzReserveManualWizard(models.TransientModel):
    """
    Wizard for manually reserving stock on a specific reservation line.
    User specifies the quantity to reserve.
    """
    _name = 'buz.reserve.manual.wizard'
    _description = 'Manual Reserve Wizard'

    line_id = fields.Many2one(
        'buz.reserve.manager.line',
        string='Reservation Line',
        required=True,
    )
    stock_move_id = fields.Many2one(
        'stock.move',
        string='Stock Move',
        required=True,
        readonly=True,
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        readonly=True,
    )
    demand_qty = fields.Float(
        string='Demand Qty',
        readonly=True,
        digits='Product Unit of Measure',
    )
    reserved_qty = fields.Float(
        string='Already Reserved',
        readonly=True,
        digits='Product Unit of Measure',
    )
    available_qty = fields.Float(
        string='Available to Reserve',
        readonly=True,
        digits='Product Unit of Measure',
    )
    reserve_qty = fields.Float(
        string='Qty to Reserve',
        digits='Product Unit of Measure',
        required=True,
        default=0.0,
    )
    max_reserve_qty = fields.Float(
        string='Max Possible',
        compute='_compute_max_reserve_qty',
        digits='Product Unit of Measure',
    )

    @api.depends('demand_qty', 'reserved_qty', 'available_qty')
    def _compute_max_reserve_qty(self):
        for rec in self:
            remaining_demand = rec.demand_qty - rec.reserved_qty
            rec.max_reserve_qty = min(remaining_demand, rec.available_qty)

    @api.onchange('max_reserve_qty')
    def _onchange_max_reserve_qty(self):
        if self.max_reserve_qty and not self.reserve_qty:
            self.reserve_qty = self.max_reserve_qty

    def action_confirm(self):
        """Execute the manual reservation."""
        self.ensure_one()
        if self.reserve_qty <= 0:
            raise ValueError(_('Please enter a quantity greater than 0.'))

        max_qty = self.max_reserve_qty
        if self.reserve_qty > max_qty:
            raise ValueError(
                _('Cannot reserve more than %.2f (demand %.2f - reserved %.2f, available %.2f)')
                % (max_qty, self.demand_qty, self.reserved_qty, self.available_qty)
            )

        # Execute manual reserve on the stock move
        move = self.stock_move_id
        try:
            move.action_manual_reserve(self.reserve_qty)
        except Exception as e:
            raise ValueError(_('Reservation failed: %s') % str(e))

        # Refresh the line
        self.line_id._refresh_line()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Reserve Complete'),
                'message': _('Successfully reserved %.2f of %s.') % (
                    self.reserve_qty, self.product_id.display_name
                ),
                'type': 'success',
                'sticky': False,
            },
        }