from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class BuzReserveManager(models.Model):
    _name = 'buz.reserve.manager'
    _description = 'Reserve Manager'
    _order = 'create_date desc'

    name = fields.Char(
        string='Reference',
        required=True,
        default=lambda self: _('New'),
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    state = fields.Selection(
        [('draft', 'Draft'), ('loaded', 'Loaded')],
        string='Status',
        default='draft',
        required=True,
    )

    sale_order_ids = fields.Many2many(
        'sale.order',
        string='Sale Orders',
        domain=[('state', 'in', ('sale', 'done'))],
    )
    partner_id = fields.Many2one('res.partner', string='Customer')
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Warehouse',
        domain="[('company_id', '=', company_id)]",
    )
    date_from = fields.Date(string='Date From')
    date_to = fields.Date(string='Date To')
    reservation_status = fields.Selection(
        [
            ('all', 'All'),
            ('none', 'Not Reserved'),
            ('partial', 'Partially Reserved'),
            ('full', 'Fully Reserved'),
        ],
        string='Reservation Status',
        default='all',
    )
    reservation_horizon_days = fields.Integer(
        string='Reservation Horizon Days',
        default=21,
        help='Moves scheduled beyond this horizon are blocked unless the session is forced or the order is already paid.',
    )
    force_reservation_override = fields.Boolean(
        string='Force Reservation Override',
        help='Allow this reservation session to lock stock even when the planned delivery date is beyond the horizon.',
    )
    product_ids = fields.Many2many('product.product', string='Products')

    bulk_action = fields.Selection(
        [('reserve', 'Reserve'), ('unreserve', 'Unreserve')],
        string='Scheduled Action',
        default='reserve',
    )
    bulk_action_at = fields.Datetime(string='Schedule At')

    line_ids = fields.One2many(
        'buz.reserve.manager.line',
        'manager_id',
        string='Reservation Lines',
    )

    summary_demand_qty = fields.Float(
        string='Total Demand',
        compute='_compute_summary',
    )
    summary_reserved_qty = fields.Float(
        string='Total Reserved',
        compute='_compute_summary',
    )
    summary_available_qty = fields.Float(
        string='Total Available',
        compute='_compute_summary',
    )
    line_count = fields.Integer(
        string='Line Count',
        compute='_compute_summary',
    )

    @api.depends('line_ids', 'line_ids.demand_qty', 'line_ids.reserved_qty', 'line_ids.available_qty')
    def _compute_summary(self):
        for manager in self:
            manager.summary_demand_qty = sum(manager.line_ids.mapped('demand_qty'))
            manager.summary_reserved_qty = sum(manager.line_ids.mapped('reserved_qty'))
            manager.summary_available_qty = sum(manager.line_ids.mapped('available_qty'))
            manager.line_count = len(manager.line_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('buz.reserve.manager') or _('New')
        return super().create(vals_list)

    def name_get(self):
        return [(rec.id, rec.name) for rec in self]

    def action_load_lines(self):
        self.ensure_one()
        if not any([
            self.sale_order_ids,
            self.partner_id,
            self.product_ids,
            self.date_from,
            self.date_to,
            self.warehouse_id,
            self.reservation_status != 'all',
        ]):
            raise UserError(_('Please specify at least one filter before loading reservation lines.'))

        existing_lines = {
            line.stock_move_id.id: line
            for line in self.line_ids
            if line.stock_move_id
        }

        domain = [
            ('state', 'in', ('draft', 'confirmed', 'waiting', 'partially_available', 'assigned')),
            ('sale_line_id', '!=', False),
            ('company_id', '=', self.company_id.id),
        ]
        if self.warehouse_id:
            domain.append(('sale_line_id.order_id.warehouse_id', '=', self.warehouse_id.id))
        if self.sale_order_ids:
            domain.append(('sale_line_id.order_id', 'in', self.sale_order_ids.ids))
        if self.partner_id:
            domain.append(('sale_line_id.order_id.partner_id', '=', self.partner_id.id))
        if self.date_from:
            domain.append(('date', '>=', self.date_from))
        if self.date_to:
            domain.append(('date', '<=', self.date_to))
        if self.product_ids:
            domain.append(('product_id', 'in', self.product_ids.ids))

        moves = self.env['stock.move'].search(domain, order='date asc, id asc')
        if not moves:
            raise UserError(self._reserve_manager_no_match_message())

        line_vals = []
        for move in moves:
            snapshot = move._reserve_manager_snapshot()
            sale_order = move.sale_line_id.order_id
            previous_line = existing_lines.get(move.id)
            line_vals.append({
                'manager_id': self.id,
                'company_id': self.company_id.id,
                'stock_move_id': move.id,
                'picking_id': move.picking_id.id,
                'sale_order_id': sale_order.id,
                'sale_line_id': move.sale_line_id.id,
                'product_id': move.product_id.id,
                'warehouse_id': self._reserve_manager_warehouse_id(move),
                'demand_qty': move.product_uom_qty,
                'reserved_qty': snapshot['reserved_qty'],
                'available_qty': snapshot['available_qty'],
                'scheduled_date': move.date,
                'reserve_state': snapshot['reserve_state'],
                'move_state': snapshot['move_state'],
                'origin': move.origin or sale_order.name,
                'scheduled_action': previous_line.scheduled_action if previous_line else False,
                'scheduled_action_at': previous_line.scheduled_action_at if previous_line else False,
                'scheduled_action_state': previous_line.scheduled_action_state if previous_line else 'idle',
                'scheduled_action_message': previous_line.scheduled_action_message if previous_line else False,
                'scheduled_action_executed_at': previous_line.scheduled_action_executed_at if previous_line else False,
                'scheduled_action_user_id': previous_line.scheduled_action_user_id.id if previous_line and previous_line.scheduled_action_user_id else False,
            })

        if self.reservation_status != 'all':
            line_vals = [vals for vals in line_vals if vals['reserve_state'] == self.reservation_status]

        if not line_vals:
            raise UserError(_('The selected reservation status filter produced no lines.'))

        self.line_ids.sudo().unlink()
        self.env['buz.reserve.manager.line'].sudo().create(line_vals)
        self.state = 'loaded'

        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_reload(self):
        self.ensure_one()
        return self.action_load_lines()

    def action_apply_schedule(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_('Load reservation lines before applying a schedule.'))
        if self.bulk_action not in ('reserve', 'unreserve'):
            raise UserError(_('Please choose Reserve or Unreserve as the scheduled action.'))
        if not self.bulk_action_at:
            raise UserError(_('Please set the schedule date and time before applying it.'))

        schedule_lines = self.line_ids
        if self.bulk_action == 'reserve':
            schedule_lines = schedule_lines.filtered(lambda line: line._reserve_manager_reserve_allowed()[0])
        if not schedule_lines:
            raise UserError(_('No lines are eligible for the selected scheduled action.'))

        schedule_lines.write({
            'scheduled_action': self.bulk_action,
            'scheduled_action_at': self.bulk_action_at,
            'scheduled_action_state': 'pending',
            'scheduled_action_message': False,
            'scheduled_action_executed_at': False,
            'scheduled_action_user_id': False,
        })
        self.state = 'loaded'
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_clear_schedule(self):
        self.ensure_one()
        self.line_ids.write({
            'scheduled_action': False,
            'scheduled_action_at': False,
            'scheduled_action_state': 'idle',
            'scheduled_action_message': False,
            'scheduled_action_executed_at': False,
            'scheduled_action_user_id': False,
        })
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_execute_due_schedules(self):
        self.ensure_one()
        due_lines = self.line_ids.filtered(
            lambda line: line.scheduled_action_state == 'pending'
            and line.scheduled_action_at
            and line.scheduled_action_at <= fields.Datetime.now()
            and line.move_state not in ('done', 'cancel')
        )
        if not due_lines:
            raise UserError(_('No scheduled actions are due right now.'))

        for line in due_lines:
            line._execute_scheduled_action(raise_on_error=False)

        self._refresh_loaded_lines()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_clear_lines(self):
        self.ensure_one()
        self.line_ids.sudo().unlink()
        self.state = 'draft'
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_reserve_all(self):
        self.ensure_one()
        lines = self.line_ids.filtered(
            lambda line: line.reserve_state in ('none', 'partial')
            and line.move_state not in ('done', 'cancel')
            and line._reserve_manager_reserve_allowed()[0]
        )
        if not lines:
            raise UserError(_('No lines are eligible to reserve under the current policy.'))

        for line in lines:
            try:
                line.stock_move_id.action_reserve_for_manager()
            except UserError:
                continue

        self._refresh_loaded_lines()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_unreserve_all(self):
        self.ensure_one()
        lines = self.line_ids.filtered(
            lambda line: line.reserve_state in ('partial', 'full') and line.move_state not in ('done', 'cancel')
        )
        if not lines:
            raise UserError(_('No lines with active reservations to unreserve.'))

        for line in lines:
            try:
                line.stock_move_id.action_unreserve_for_manager(
                    unreserve_type='bulk_picking',
                    reason=_('Reserve Manager'),
                )
            except UserError:
                continue

        self._refresh_loaded_lines()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def _refresh_loaded_lines(self):
        for manager in self:
            for line in manager.line_ids:
                line._refresh_from_move()

    def _reserve_manager_no_match_message(self):
        self.ensure_one()
        base_domain = [
            ('sale_line_id', '!=', False),
            ('company_id', '=', self.company_id.id),
        ]
        if self.warehouse_id:
            base_domain.append(('sale_line_id.order_id.warehouse_id', '=', self.warehouse_id.id))
        if self.sale_order_ids:
            base_domain.append(('sale_line_id.order_id', 'in', self.sale_order_ids.ids))
        if self.partner_id:
            base_domain.append(('sale_line_id.order_id.partner_id', '=', self.partner_id.id))
        if self.date_from:
            base_domain.append(('date', '>=', self.date_from))
        if self.date_to:
            base_domain.append(('date', '<=', self.date_to))
        if self.product_ids:
            base_domain.append(('product_id', 'in', self.product_ids.ids))

        related_moves = self.env['stock.move'].search(base_domain)
        filters = []
        if self.sale_order_ids:
            filters.append(_('SO(s): %s') % ', '.join(self.sale_order_ids.mapped('display_name')))
        if self.partner_id:
            filters.append(_('Customer: %s') % self.partner_id.display_name)
        if self.warehouse_id:
            filters.append(_('Warehouse: %s') % self.warehouse_id.display_name)
        if self.product_ids:
            filters.append(_('Product(s): %s') % ', '.join(self.product_ids.mapped('display_name')))
        if self.date_from:
            filters.append(_('From: %s') % self.date_from)
        if self.date_to:
            filters.append(_('To: %s') % self.date_to)
        if self.reservation_status != 'all':
            filters.append(
                _('Reservation status: %s')
                % dict(self._fields['reservation_status'].selection).get(self.reservation_status, self.reservation_status)
            )

        if related_moves:
            state_order = ['draft', 'confirmed', 'waiting', 'partially_available', 'assigned', 'done', 'cancel']
            state_labels = {
                'draft': _('Draft'),
                'confirmed': _('Confirmed'),
                'waiting': _('Waiting'),
                'partially_available': _('Partially Available'),
                'assigned': _('Assigned'),
                'done': _('Done'),
                'cancel': _('Cancelled'),
            }
            state_summary = ', '.join(
                '%s: %s' % (
                    state_labels.get(state, state),
                    count,
                )
                for state in state_order
                for count in [self.env['stock.move'].search_count(base_domain + [('state', '=', state)])]
                if count
            )
            return _(
                'No open delivery moves matched the selected filters.\n\n'
                'These filters still found %d move(s), but they are all outside the loadable states.\n'
                'Move states: %s\n\n'
                'Selected filters:\n%s'
            ) % (
                len(related_moves),
                state_summary or _('(no state summary available)'),
                '\n'.join(filters) or _('(none)'),
            )

        return _(
            'No delivery moves matched the selected filters.\n\n'
            'Selected filters:\n%s'
        ) % ('\n'.join(filters) or _('(none)'))

    def _reserve_manager_warehouse_id(self, move):
        self.ensure_one()
        if move.warehouse_id:
            return move.warehouse_id.id
        if move.sale_line_id.order_id.warehouse_id:
            return move.sale_line_id.order_id.warehouse_id.id
        picking_type = move.picking_id.picking_type_id if move.picking_id else False
        if picking_type and picking_type.warehouse_id:
            return picking_type.warehouse_id.id
        return False

    def _reserve_manager_move_is_paid(self, move):
        self.ensure_one()
        sale_order = move.sale_line_id.order_id
        invoices = sale_order.invoice_ids.filtered(
            lambda invoice: invoice.state == 'posted' and invoice.move_type == 'out_invoice'
        )
        return any(
            invoice.payment_state in ('paid', 'overpaid') or not invoice.amount_residual
            for invoice in invoices
        )

    def _reserve_manager_reserve_allowed(self, move):
        self.ensure_one()
        if self.force_reservation_override:
            return True, _('Manual override is enabled for this reservation session.')
        if self._reserve_manager_move_is_paid(move):
            return True, _('Posted paid invoice detected for this sales order.')

        planned_date = fields.Datetime.to_datetime(move.date).date() if move.date else False
        if not planned_date:
            return True, _('No delivery plan date is set.')

        horizon_days = self.reservation_horizon_days or 21
        limit_date = fields.Date.context_today(self) + relativedelta(days=horizon_days)
        if planned_date > limit_date:
            return False, _(
                'Planned delivery date %(planned)s exceeds the %(days)s-day reservation window.'
            ) % {
                'planned': planned_date,
                'days': horizon_days,
            }
        return True, _(
            'Planned delivery date %(planned)s is within the %(days)s-day reservation window.'
        ) % {
            'planned': planned_date,
            'days': horizon_days,
        }


class BuzReserveManagerLine(models.Model):
    _name = 'buz.reserve.manager.line'
    _description = 'Reserve Manager Line'
    _order = 'scheduled_action_at asc, scheduled_date asc, id asc'

    manager_id = fields.Many2one(
        'buz.reserve.manager',
        string='Manager',
        required=True,
        ondelete='cascade',
    )
    company_id = fields.Many2one(
        'res.company',
        related='manager_id.company_id',
        store=True,
        readonly=True,
    )
    stock_move_id = fields.Many2one(
        'stock.move',
        string='Stock Move',
        readonly=True,
        ondelete='set null',
    )
    picking_id = fields.Many2one(
        'stock.picking',
        string='Delivery',
        readonly=True,
        ondelete='set null',
    )
    sale_order_id = fields.Many2one('sale.order', string='Sale Order', readonly=True)
    sale_line_id = fields.Many2one('sale.order.line', string='SO Line', readonly=True)
    product_id = fields.Many2one('product.product', string='Product', readonly=True)
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse', readonly=True)
    demand_qty = fields.Float(string='Demand Qty', digits='Product Unit of Measure', readonly=True)
    reserved_qty = fields.Float(string='Reserved Qty', digits='Product Unit of Measure', readonly=True)
    available_qty = fields.Float(string='Available Qty', digits='Product Unit of Measure', readonly=True)
    scheduled_date = fields.Datetime(string='Scheduled Date', readonly=True)
    reserve_state = fields.Selection(
        [('none', 'Not Reserved'), ('partial', 'Partially Reserved'), ('full', 'Fully Reserved')],
        string='Reserve Status',
        readonly=True,
    )
    move_state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('waiting', 'Waiting'),
            ('confirmed', 'Confirmed'),
            ('partially_available', 'Partially Available'),
            ('assigned', 'Assigned'),
            ('done', 'Done'),
            ('cancel', 'Cancelled'),
        ],
        string='Move State',
        readonly=True,
    )
    origin = fields.Char(string='Origin', readonly=True)
    scheduled_action = fields.Selection(
        [('reserve', 'Reserve'), ('unreserve', 'Unreserve')],
        string='Scheduled Action',
    )
    scheduled_action_at = fields.Datetime(string='Scheduled At')
    scheduled_action_state = fields.Selection(
        [
            ('idle', 'Idle'),
            ('pending', 'Pending'),
            ('running', 'Running'),
            ('done', 'Done'),
            ('failed', 'Failed'),
        ],
        string='Schedule Status',
        default='idle',
        readonly=True,
    )
    scheduled_action_message = fields.Text(string='Schedule Message', readonly=True)
    scheduled_action_executed_at = fields.Datetime(string='Executed At', readonly=True)
    scheduled_action_user_id = fields.Many2one('res.users', string='Executed By', readonly=True)
    reserve_policy_state = fields.Selection(
        [
            ('allowed', 'Allowed'),
            ('paid', 'Paid Override'),
            ('blocked', 'Blocked'),
        ],
        string='Reserve Policy',
        compute='_compute_reserve_policy',
    )
    reserve_policy_message = fields.Char(
        string='Policy Note',
        compute='_compute_reserve_policy',
    )

    @api.depends('scheduled_date', 'sale_order_id.partner_id', 'sale_order_id.invoice_ids.payment_state', 'manager_id.reservation_horizon_days', 'manager_id.force_reservation_override')
    def _compute_reserve_policy(self):
        for line in self:
            if not line.stock_move_id:
                line.reserve_policy_state = 'blocked'
                line.reserve_policy_message = _('Stock move not found.')
                continue
            allowed, message = line._reserve_manager_reserve_allowed()
            if line.manager_id.force_reservation_override:
                line.reserve_policy_state = 'allowed'
            elif line.manager_id._reserve_manager_move_is_paid(line.stock_move_id):
                line.reserve_policy_state = 'paid'
            elif allowed:
                line.reserve_policy_state = 'allowed'
            else:
                line.reserve_policy_state = 'blocked'
            line.reserve_policy_message = message

    def _reserve_manager_reserve_allowed(self):
        self.ensure_one()
        if not self.stock_move_id:
            return False, _('Stock move not found.')
        return self.manager_id._reserve_manager_reserve_allowed(self.stock_move_id)

    @api.model
    def _cron_process_due_scheduled_actions(self, batch_size=200):
        now = fields.Datetime.now()
        due_lines = self.search([
            ('scheduled_action_state', '=', 'pending'),
            ('scheduled_action_at', '!=', False),
            ('scheduled_action_at', '<=', now),
            ('move_state', 'not in', ('done', 'cancel')),
        ], order='scheduled_action_at asc, id asc', limit=batch_size)
        for line in due_lines:
            line._execute_scheduled_action(raise_on_error=False)
        return True

    def action_reserve(self):
        self.ensure_one()
        if not self.stock_move_id.exists():
            raise UserError(_('Stock move not found.'))
        allowed, message = self._reserve_manager_reserve_allowed()
        if not allowed:
            raise UserError(message)

        self.stock_move_id.action_reserve_for_manager()
        self.manager_id._refresh_loaded_lines()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_unreserve(self):
        self.ensure_one()
        if not self.stock_move_id.exists():
            raise UserError(_('Stock move not found.'))
        if self.reserve_state not in ('partial', 'full'):
            raise UserError(_('This line has no reservation to unreserve.'))

        self.stock_move_id.action_unreserve_for_manager(
            unreserve_type='picking',
            reason=_('Reserve Manager'),
        )
        self.manager_id._refresh_loaded_lines()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def _execute_scheduled_action(self, raise_on_error=False):
        self.ensure_one()
        now = fields.Datetime.now()

        if self.scheduled_action_state != 'pending':
            return False
        if not self.scheduled_action_at or self.scheduled_action_at > now:
            return False
        if not self.stock_move_id.exists():
            self.write({
                'scheduled_action_state': 'failed',
                'scheduled_action_message': _('Stock move not found.'),
                'scheduled_action_executed_at': now,
                'scheduled_action_user_id': self.env.uid,
            })
            if raise_on_error:
                raise UserError(_('Stock move not found.'))
            return False

        self.write({
            'scheduled_action_state': 'running',
            'scheduled_action_message': False,
        })

        try:
            if self.scheduled_action == 'reserve':
                allowed, message = self._reserve_manager_reserve_allowed()
                if not allowed:
                    raise UserError(message)
                self.stock_move_id.action_reserve_for_manager()
                self._refresh_from_move()
                if self.reserve_state == 'none':
                    raise UserError(_('No stock could be reserved for this move.'))
                message = _('Reservation completed.') if self.reserve_state == 'full' else _('Reservation completed partially.')
            elif self.scheduled_action == 'unreserve':
                if self.reserve_state == 'none':
                    message = _('Nothing to unreserve.')
                else:
                    self.stock_move_id.action_unreserve_for_manager(
                        unreserve_type='scheduled',
                        reason=_('Reserve Manager'),
                    )
                    self._refresh_from_move()
                    message = _('Reservation released.')
            else:
                raise UserError(_('Please choose a valid scheduled action.'))

            self.write({
                'scheduled_action_state': 'done',
                'scheduled_action_message': message,
                'scheduled_action_executed_at': now,
                'scheduled_action_user_id': self.env.uid,
            })
            return True
        except UserError as exc:
            self.write({
                'scheduled_action_state': 'failed',
                'scheduled_action_message': str(exc),
                'scheduled_action_executed_at': now,
                'scheduled_action_user_id': self.env.uid,
            })
            if raise_on_error:
                raise
            return False

    def action_open_sale_order(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sale Order'),
            'res_model': 'sale.order',
            'res_id': self.sale_order_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_open_picking(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Delivery'),
            'res_model': 'stock.picking',
            'res_id': self.picking_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _refresh_from_move(self):
        for line in self:
            move = line.stock_move_id
            if not move.exists() or move.state in ('done', 'cancel'):
                line.sudo().unlink()
                continue

            snapshot = move._reserve_manager_snapshot()
            line.write({
                'picking_id': move.picking_id.id,
                'sale_order_id': move.sale_line_id.order_id.id,
                'sale_line_id': move.sale_line_id.id,
                'product_id': move.product_id.id,
                'warehouse_id': line.manager_id._reserve_manager_warehouse_id(move),
                'demand_qty': move.product_uom_qty,
                'reserved_qty': snapshot['reserved_qty'],
                'available_qty': snapshot['available_qty'],
                'scheduled_date': move.date,
                'reserve_state': snapshot['reserve_state'],
                'move_state': snapshot['move_state'],
                'origin': move.origin or move.sale_line_id.order_id.name,
            })
