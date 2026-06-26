from odoo import models, fields, api, _
from odoo.exceptions import UserError


class BuzReserveManager(models.Model):
    """
    Reserve Manager – Dashboard for managing stock reservations
    linked to Sales Orders.

    Workflow:
    1. User creates a new manager record
    2. Sets filters: Sale Orders, date range, products
    3. Clicks "Load Lines" to populate reservation data
    4. Each line shows: product, demanded qty, reserved qty, etc.
    5. User can click "Reserve" or "Unreserve" per line
    6. Or "Unreserve All" per SO to bulk-release
    """
    _name = 'buz.reserve.manager'
    _description = 'Reserve Manager'
    _order = 'create_date desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Reference',
        required=True,
        default=lambda self: _('New'),
        readonly=True,
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('loaded', 'Loaded'),
    ], string='Status', default='draft', tracking=True)

    # -------------------------------------------------------------------------
    # Filter fields
    # -------------------------------------------------------------------------
    sale_order_ids = fields.Many2many(
        'sale.order',
        string='Sale Orders',
        domain=[('state', 'in', ('sale', 'done'))],
    )
    date_from = fields.Date(string='Date From')
    date_to = fields.Date(string='Date To')
    product_ids = fields.Many2many(
        'product.product',
        string='Products',
    )
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Warehouse',
        default=lambda self: self.env.user._get_default_warehouse_id(),
    )

    # -------------------------------------------------------------------------
    # Lines
    # -------------------------------------------------------------------------
    line_ids = fields.One2many(
        'buz.reserve.manager.line',
        'manager_id',
        string='Reservation Lines',
    )

    summary_demand_qty = fields.Float(
        string='Total Demand', compute='_compute_summary', store=False
    )
    summary_reserved_qty = fields.Float(
        string='Total Reserved', compute='_compute_summary', store=False
    )
    summary_available_qty = fields.Float(
        string='Total Available', compute='_compute_summary', store=False
    )
    line_count = fields.Integer(
        string='Line Count', compute='_compute_summary', store=False
    )

    @api.depends('line_ids')
    def _compute_summary(self):
        for rec in self:
            rec.summary_demand_qty = sum(rec.line_ids.mapped('demand_qty'))
            rec.summary_reserved_qty = sum(rec.line_ids.mapped('reserved_qty'))
            rec.summary_available_qty = sum(rec.line_ids.mapped('available_qty'))
            rec.line_count = len(rec.line_ids)

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------
    def action_load_lines(self):
        """Load reservation lines based on current filter criteria."""
        self.ensure_one()
        # Clear existing lines
        self.line_ids.unlink()

        # Require at least one filter to prevent loading everything
        if not any([self.sale_order_ids, self.product_ids, self.date_from, self.date_to]):
            raise UserError(_(
                'Please specify at least one filter — Sale Orders, Products, '
                'or a Date Range — before loading lines.'
            ))

        domain = [('state', 'not in', ('done', 'cancel'))]

        # Filter by sale order (optional)
        if self.sale_order_ids:
            domain.append(('sale_line_id.order_id', 'in', self.sale_order_ids.ids))

        # Filter by date range (scheduled date on stock.move)
        if self.date_from:
            domain.append(('date', '>=', self.date_from))
        if self.date_to:
            domain.append(('date', '<=', self.date_to))

        # Filter by product
        if self.product_ids:
            domain.append(('product_id', 'in', self.product_ids.ids))

        # Only show moves that have a sale_line_id (sale-related)
        domain.append(('sale_line_id', '!=', False))

        # Warehouse filter
        if self.warehouse_id:
            domain.append(('warehouse_id', '=', self.warehouse_id.id))

        moves = self.env['stock.move'].search(domain, order='date asc', limit=500)

        if not moves:
            criteria_parts = []
            if self.warehouse_id:
                criteria_parts.append(_('Warehouse: %s') % self.warehouse_id.display_name)
            if self.date_from:
                criteria_parts.append(_('From: %s') % self.date_from)
            if self.date_to:
                criteria_parts.append(_('To: %s') % self.date_to)
            if self.product_ids:
                criteria_parts.append(_('Products: %s') % ', '.join(self.product_ids.mapped('display_name')))
            if self.sale_order_ids:
                criteria_parts.append(_('SOs: %s') % ', '.join(self.sale_order_ids.mapped('display_name')))
            criteria_str = '\n'.join(criteria_parts) if criteria_parts else _('(no filters)')
            raise UserError(_(
                'No matching reservation lines found for the given criteria.\n\n'
                '%s\n\n'
                'Tips:\n'
                '• Check the product — it must have an active Sale Order with confirmed/done stock moves\n'
                '• Try a wider date range\n'
                '• Try removing the warehouse filter first'
            ) % criteria_str)

        line_vals = []
        move_reserve_states = {}
        for move in moves:
            # Calculate reserved qty from move lines
            reserved_qty = sum(move.move_line_ids.mapped('quantity'))

            # Determine reservation status
            if move.state == 'assigned' and reserved_qty >= move.product_uom_qty:
                reserve_state = 'full'
            elif reserved_qty > 0:
                reserve_state = 'partial'
            else:
                reserve_state = 'none'

            # Get available stock for this product at the source location
            available_qty = self._get_available_for_move(move)

            line_vals.append({
                'manager_id': self.id,
                'stock_move_id': move.id,
                'sale_order_id': move.sale_line_id.order_id.id,
                'sale_line_id': move.sale_line_id.id,
                'product_id': move.product_id.id,
                'demand_qty': move.product_uom_qty,
                'reserved_qty': reserved_qty,
                'available_qty': available_qty,
                'scheduled_date': move.date,
                'reserve_state': reserve_state,
                'origin': move.origin or move.sale_line_id.order_id.name,
            })

        # Batch create lines for performance
        if line_vals:
            self.env['buz.reserve.manager.line'].create(line_vals)

        self.state = 'loaded'
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Lines Loaded'),
                'message': _('%d reservation line(s) loaded.') % len(line_vals),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_clear_lines(self):
        """Clear current lines and reset to draft."""
        self.ensure_one()
        self.line_ids.unlink()
        self.state = 'draft'

    def action_unreserve_all(self):
        """Unreserve all lines in this manager session."""
        self.ensure_one()
        lines_to_unreserve = self.line_ids.filtered(
            lambda l: l.reserve_state in ('full', 'partial')
        )
        if not lines_to_unreserve:
            raise UserError(_('No lines with active reservations to unreserve.'))

        count = 0
        for line in lines_to_unreserve:
            try:
                line.action_unreserve()
                count += 1
            except UserError:
                continue

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Unreserve Complete'),
                'message': _('%d line(s) unreserved successfully.') % count,
                'type': 'success',
                'sticky': False,
            },
        }

    def action_reload(self):
        """Reload lines with same filters."""
        self.ensure_one()
        return self.action_load_lines()

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------
    def _get_available_for_move(self, move):
        """Compute available-to-reserve qty for the move's product/location."""
        return self.env['stock.quant']._get_available_quantity(
            move.product_id,
            move.location_id,
        )

    # -------------------------------------------------------------------------
    # Sequence
    # -------------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'buz.reserve.manager'
                ) or _('New')
        return super().create(vals_list)

    def name_get(self):
        return [(rec.id, rec.name) for rec in self]


class BuzReserveManagerLine(models.Model):
    """
    Individual reservation line within a Reserve Manager session.
    Each line represents one stock.move linked to a Sale Order.
    """
    _name = 'buz.reserve.manager.line'
    _description = 'Reserve Manager Line'
    _order = 'scheduled_date asc, id asc'

    manager_id = fields.Many2one(
        'buz.reserve.manager',
        string='Manager',
        required=True,
        ondelete='cascade',
    )
    stock_move_id = fields.Many2one(
        'stock.move',
        string='Stock Move',
        readonly=True,
        ondelete='set null',
    )
    sale_order_id = fields.Many2one(
        'sale.order',
        string='Sale Order',
        readonly=True,
    )
    sale_line_id = fields.Many2one(
        'sale.order.line',
        string='SO Line',
        readonly=True,
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        readonly=True,
    )
    demand_qty = fields.Float(
        string='Demand Qty',
        digits='Product Unit of Measure',
        readonly=True,
    )
    reserved_qty = fields.Float(
        string='Reserved Qty',
        digits='Product Unit of Measure',
        readonly=True,
    )
    available_qty = fields.Float(
        string='Available Qty',
        digits='Product Unit of Measure',
        readonly=True,
        help='Stock available to reserve at source location.',
    )
    scheduled_date = fields.Datetime(
        string='Scheduled Date',
        readonly=True,
    )
    reserve_state = fields.Selection([
        ('none', 'Not Reserved'),
        ('partial', 'Partially Reserved'),
        ('full', 'Fully Reserved'),
    ], string='Reserve Status', readonly=True)
    origin = fields.Char(string='Origin', readonly=True)

    # -------------------------------------------------------------------------
    # Actions on lines
    # -------------------------------------------------------------------------
    def action_reserve(self):
        """Open wizard to manually reserve this line."""
        self.ensure_one()
        if not self.exists():
            raise UserError(_(
                'This line no longer exists. '
                'It may have been removed by another session. '
                'Please reload the reservation lines.'
            ))
        if not self.stock_move_id:
            raise UserError(_('Stock move not found.'))

        # Open manual reserve wizard
        view = self.env.ref('buz_reserve_manager.view_manual_reserve_wizard_form')
        wizard = self.env['buz.reserve.manual.wizard'].create({
            'line_id': self.id,
            'stock_move_id': self.stock_move_id.id,
            'product_id': self.product_id.id,
            'demand_qty': self.demand_qty,
            'reserved_qty': self.reserved_qty,
            'available_qty': self.available_qty,
        })

        return {
            'name': _('Manual Reserve'),
            'type': 'ir.actions.act_window',
            'res_model': 'buz.reserve.manual.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'view_id': view.id,
            'target': 'new',
            'context': {},
        }

    def action_unreserve(self):
        """Unreserve this single line."""
        self.ensure_one()
        if not self.exists():
            raise UserError(_(
                'This line no longer exists. '
                'It may have been removed by another session. '
                'Please reload the reservation lines.'
            ))
        if not self.stock_move_id:
            raise UserError(_('Stock move not found.'))
        if self.reserve_state not in ('full', 'partial'):
            raise UserError(_('This line has no reservation to unreserve.'))

        self.stock_move_id.action_unreserve_single()
        return self._refresh_line()

    def action_unreserve_by_so(self):
        """Unreserve ALL lines belonging to the same Sale Order."""
        self.ensure_one()
        if not self.exists():
            raise UserError(_(
                'This line no longer exists. '
                'It may have been removed by another session. '
                'Please reload the reservation lines.'
            ))
        so_lines = self.search([
            ('manager_id', '=', self.manager_id.id),
            ('sale_order_id', '=', self.sale_order_id.id),
            ('reserve_state', 'in', ('full', 'partial')),
        ])
        if not so_lines:
            raise UserError(_('No reserved lines found for this Sale Order.'))

        count = 0
        for line in so_lines:
            try:
                line.stock_move_id.action_unreserve_single()
                count += 1
            except (UserError, Exception):
                continue

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Unreserved'),
                'message': _('%d line(s) unreserved for SO %s.') % (
                    count, self.sale_order_id.display_name
                ),
                'type': 'success',
                'sticky': False,
            },
        }

    def _refresh_line(self):
        """Refresh line data after a reserve/unreserve action."""
        self.ensure_one()
        if not self.exists():
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Not Found'),
                    'message': _('This line no longer exists. Please reload the reservation lines.'),
                    'type': 'warning',
                    'sticky': False,
                },
            }
        move = self.stock_move_id
        if not move.exists():
            self.unlink()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Removed'),
                    'message': _('Stock move no longer exists. Line removed.'),
                    'type': 'info',
                    'sticky': False,
                },
            }

        # Recalculate
        reserved_qty = sum(move.move_line_ids.mapped('quantity'))
        if move.state == 'assigned' and reserved_qty >= move.product_uom_qty:
            reserve_state = 'full'
        elif reserved_qty > 0:
            reserve_state = 'partial'
        else:
            reserve_state = 'none'

        self.write({
            'reserved_qty': reserved_qty,
            'reserve_state': reserve_state,
            'available_qty': self.manager_id._get_available_for_move(move),
        })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Updated'),
                'message': _('Line updated. Reserve status: %s') % dict(
                    self._fields['reserve_state'].selection
                ).get(reserve_state, reserve_state),
                'type': 'success',
                'sticky': False,
            },
        }