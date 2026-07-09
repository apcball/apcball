from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)

WALK_IN_CUSTOMER_NAME = 'Walk-in Customer'

# ─── Trade Channel Mapping ────────────────────────────────────
# Auto-maps POS Lite channel → marketplace_settlement.trade_channel
# when the user hasn't explicitly chosen a trade_channel.
POS_CHANNEL_TO_TRADE_CHANNEL = {
    'phone': 'online_line_fb',
    'line': 'online_line_fb',
    'walkin': 'offline_mogen_outlet',
    'other': 'other',
}


def _get_trade_channel_selection(self):
    """Return the selection marketplace.settlement injects into sale.order.trade_channel.

    marketplace_settlement adds trade_channel to sale.order via _inherit.
    If the module is installed, the field will carry the canonical selection;
    if not, use a hardcoded fallback.
    """
    SO = self.env.get('sale.order')
    if SO:
        field = SO._fields.get('trade_channel')
        if field and field.selection:
            return field.selection
    # Fallback if marketplace_settlement is not installed
    return [
        ('shopee', 'Shopee'),
        ('lazada', 'Lazada'),
        ('nocnoc', 'Noc Noc'),
        ('tiktok', 'Tiktok'),
        ('spx', 'SPX'),
        ('online_line_fb', 'ONLINE/Line + Facebook'),
        ('offline_mogen_outlet', 'OFFLINE/Mogen Outlet'),
        ('after_sale_service', 'After sale service'),
        ('installation_service', 'Installation service'),
        ('own_channel_cdc', 'Own channel ( CDC )'),
        ('other', 'Other'),
    ]


class PosLiteOrder(models.Model):
    _name = 'pos.lite.order'
    _description = 'POS Lite Order'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'
    _rec_name = 'name'

    name = fields.Char(default='/', copy=False, readonly=True, tracking=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id', store=True, readonly=True)

    @api.model
    def _selection_trade_channel(self):
        """Dynamic selection mirroring marketplace.settlement.trade_channel."""
        return _get_trade_channel_selection(self)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('held', 'Held'),
        ('paid', 'Paid'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], default='draft', required=True, tracking=True)
    channel = fields.Selection([
        ('phone', 'Phone'),
        ('line', 'LINE'),
        ('walkin', 'Walk-in'),
        ('other', 'Other'),
    ], default='phone', required=True, tracking=True)
    trade_channel = fields.Selection(
        selection='_selection_trade_channel',
        string='Trade Channel',
        help="Marketplace trade channel for settlement grouping. "
             "Auto-mapped from POS channel when empty.",
        tracking=True,
    )
    customer_name = fields.Char(tracking=True)
    partner_id = fields.Many2one('res.partner', tracking=True, check_company=True)
    partner_phone = fields.Char(tracking=True)
    partner_address = fields.Char(tracking=True)
    partner_invoice_id = fields.Many2one('res.partner', string='Invoice Address', domain="['|', ('parent_id', '=', partner_id), ('id', '=', partner_id)]")
    partner_shipping_id = fields.Many2one('res.partner', string='Delivery Address', domain="['|', ('parent_id', '=', partner_id), ('id', '=', partner_id)]")
    partner_tax_id = fields.Char(tracking=True)
    warehouse_id = fields.Many2one(
        'stock.warehouse', required=True,
        domain="[('company_id', '=', company_id)]",
        tracking=True, check_company=True,
    )
    pricelist_id = fields.Many2one(
        'product.pricelist', required=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        tracking=True, check_company=True,
    )
    session_id = fields.Many2one(
        'pos.lite.session', string='Session',
        tracking=True, index=True,
        domain="[('state', '=', 'opened'), ('company_id', '=', company_id)]",
        check_company=True,
    )
    employee_id = fields.Many2one(
        'hr.employee', string='Employee',
        tracking=True, check_company=True,
        domain="[('company_id', '=', company_id)]",
    )
    line_ids = fields.One2many('pos.lite.order.line', 'order_id', string='Order Lines')
    payment_ids = fields.One2many('pos.lite.payment', 'order_id', string='Payments')
    amount_untaxed = fields.Monetary(compute='_compute_amounts', store=True)
    amount_tax = fields.Monetary(compute='_compute_amounts', store=True)
    amount_total = fields.Monetary(compute='_compute_amounts', store=True)
    amount_paid = fields.Monetary(compute='_compute_amounts', store=True)
    amount_residual = fields.Monetary(compute='_compute_amounts', store=True)
    amount_change = fields.Monetary(compute='_compute_amounts', store=True)
    margin = fields.Monetary(
        string="Margin",
        compute='_compute_margin',
        store=True,
        currency_field='currency_id',
        help="Sales margin = revenue − standard cost, sourced from the "
             "company's Standard Cost Pricelist (same source as Sales Orders).",
    )
    margin_percent = fields.Float(
        string="Margin %",
        compute='_compute_margin',
        store=True,
        help="Margin as a fraction of the untaxed amount (margin / amount_untaxed), "
             "displayed with the percentage widget. Matches Sales Orders.",
    )
    invoice_id = fields.Many2one('account.move', readonly=True, copy=False)
    picking_id = fields.Many2one('stock.picking', readonly=True, copy=False)
    is_return = fields.Boolean(default=False, copy=False, tracking=True)
    return_status = fields.Char(compute='_compute_return_exchange_status', string='Return Status')
    return_of_order_id = fields.Many2one('pos.lite.order', readonly=True, copy=False, tracking=True, index=True)
    return_order_ids = fields.One2many('pos.lite.order', 'return_of_order_id', string='Return Orders')
    return_reason = fields.Text(copy=False)
    return_count = fields.Integer(compute='_compute_return_count', string='Returns')
    is_exchange = fields.Boolean(default=False, copy=False, tracking=True)
    exchange_status = fields.Char(compute='_compute_return_exchange_status', string='Exchange Status')
    exchange_of_order_id = fields.Many2one('pos.lite.order', readonly=True, copy=False, tracking=True, index=True)
    exchange_order_ids = fields.One2many('pos.lite.order', 'exchange_of_order_id', string='Exchange Orders')
    exchange_return_order_id = fields.Many2one('pos.lite.order', readonly=True, copy=False, string='Exchange Return',
                                               help='For exchange orders: links to the associated return order')
    exchange_count = fields.Integer(compute='_compute_exchange_count', string='Exchanges')
    exchange_return_total = fields.Monetary(compute='_compute_exchange_summary', string='Return Value (Exchange)')
    exchange_new_total = fields.Monetary(compute='_compute_exchange_summary', string='New Items Value (Exchange)')
    exchange_difference = fields.Monetary(compute='_compute_exchange_summary', string='Exchange Difference')
    exchange_customer_pays = fields.Boolean(compute='_compute_exchange_summary', string='Customer Pays Extra')
    exchange_customer_gets_refund = fields.Boolean(compute='_compute_exchange_summary', string='Customer Gets Refund')
    note = fields.Text()
    date_order = fields.Datetime(
        string='Order Date', default=fields.Datetime.now, readonly=True, tracking=True,
    )

    _ALLOWED_TRANSITIONS = {
        'draft': {'held', 'paid', 'done', 'cancelled'},
        'held': {'draft', 'cancelled'},
        'paid': {'done', 'cancelled'},
        'done': set(),
        'cancelled': set(),
    }

    def write(self, vals):
        if 'state' in vals:
            new_state = vals['state']
            for order in self:
                allowed = self._ALLOWED_TRANSITIONS.get(order.state, set())
                if new_state != order.state and new_state not in allowed:
                    raise UserError(_(
                        'Invalid state transition: %s → %s. Use the proper action buttons.'
                    ) % (order.state, new_state))
        return super().write(vals)

    _sql_constraints = [
        ('name_unique', 'unique(name)', 'Order number must be unique.'),
    ]

    # ─── Compute ────────────────────────────────────────────────

    @api.depends('line_ids', 'line_ids.price_subtotal', 'line_ids.price_tax',
                 'payment_ids', 'payment_ids.amount', 'is_return')
    def _compute_amounts(self):
        for order in self:
            untaxed = sum(order.line_ids.mapped('price_subtotal'))
            tax = sum(order.line_ids.mapped('price_tax'))
            paid = sum(order.payment_ids.mapped('amount'))
            total = untaxed + tax
            # Return orders: total and amounts are negative (like standard credit notes).
            # payments are negative for returns (refund). residual = -(abs_total - abs_paid).
            if order.is_return:
                order.amount_untaxed = -untaxed
                order.amount_tax = -tax
                order.amount_total = -total
                order.amount_paid = paid
                # abs(total) - abs(paid); remaining refund owed to customer is negative.
                order.amount_residual = -(max(total + paid, 0.0))
                order.amount_change = 0.0
            else:
                order.amount_untaxed = untaxed
                order.amount_tax = tax
                order.amount_total = total
                order.amount_paid = paid
                order.amount_residual = max(total - paid, 0.0)
                order.amount_change = max(paid - total, 0.0)

    @api.depends('line_ids.margin', 'amount_untaxed', 'is_return')
    def _compute_margin(self):
        # Mirrors buz_sale_pricelist_standard_cost's sale.order margin: line
        # margins summed, then margin_percent = margin / amount_untaxed.
        # Returns reverse the profit impact (refund revenue + recover cost),
        # consistent with how amount_untaxed is negated for return orders.
        for order in self:
            line_margin = sum(order.line_ids.mapped('margin'))
            order.margin = -line_margin if order.is_return else line_margin
            order.margin_percent = order.amount_untaxed and (order.margin / order.amount_untaxed) or 0.0

    @api.depends('is_return', 'is_exchange')
    def _compute_return_exchange_status(self):
        for order in self:
            order.return_status = _('Return') if order.is_return else _('Sale')
            order.exchange_status = _('Exchange') if order.is_exchange else _('Direct')

    @api.depends('return_order_ids')
    def _compute_return_count(self):
        for order in self:
            order.return_count = len(order.return_order_ids)

    @api.depends('exchange_order_ids')
    def _compute_exchange_count(self):
        for order in self:
            order.exchange_count = len(order.exchange_order_ids)

    @api.depends('exchange_order_ids', 'exchange_order_ids.amount_total',
                 'exchange_return_order_id', 'exchange_return_order_id.amount_total')
    def _compute_exchange_summary(self):
        """คำนวณมูลค่า return items, new items, และส่วนต่าง สำหรับ original order ที่มี exchange"""
        for order in self:
            if not order.is_exchange:
                # Original order → หา exchange orders
                ret_total = 0.0
                new_total = 0.0
                for ex in order.exchange_order_ids:
                    if ex.exchange_return_order_id:
                        ret_total += ex.exchange_return_order_id.amount_total
                    new_total += ex.amount_total
                order.exchange_return_total = ret_total
                order.exchange_new_total = new_total
                order.exchange_difference = new_total - ret_total
                order.exchange_customer_pays = (new_total - ret_total) > 0.01
                order.exchange_customer_gets_refund = (new_total - ret_total) < -0.01
            else:
                # Exchange order → ดูของตัวเอง
                ret = order.exchange_return_order_id
                order.exchange_return_total = ret.amount_total if ret else 0.0
                order.exchange_new_total = order.amount_total
                order.exchange_difference = order.amount_total - (ret.amount_total if ret else 0.0)
                order.exchange_customer_pays = False
                order.exchange_customer_gets_refund = False

    # ─── CRUD ───────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/' or not vals.get('name'):
                vals['name'] = self.env['ir.sequence']._safe_next_by_code(
                    'pos.lite.order', 'pos.lite.order', prefix='POS',
                )
            # Auto-set trade_channel from POS channel when not explicitly provided.
            # This ensures terminal orders (created via controller) also get a trade_channel.
            if not vals.get('trade_channel') and vals.get('channel'):
                mapped = POS_CHANNEL_TO_TRADE_CHANNEL.get(vals['channel'])
                if mapped:
                    vals['trade_channel'] = mapped
        orders = super().create(vals_list)
        for order in orders:
            if order.is_return:
                continue
            if not order.session_id:
                # Find employee of current user
                employee = self.env['hr.employee'].search([
                    ('user_id', '=', self.env.uid),
                    ('company_id', '=', order.company_id.id),
                ], limit=1)
                if employee:
                    session = self.env['pos.lite.session'].search([
                        ('state', '=', 'opened'),
                        '|',
                        ('employee_id', '=', employee.id),
                        ('employee_ids', '=', employee.id),
                        ('company_id', '=', order.company_id.id),
                    ], limit=1)
                    if session:
                        order.session_id = session.id
                # No catch-all fallback: assigning another employee's session
                # silently would misattribute sales. Surface the error instead.
            # Validate: must have open session
            if not order.session_id:
                raise UserError(_(
                    'ไม่สามารถสร้างออเดอร์ได้: ไม่พบ Session ที่เปิดอยู่ '
                    'กรุณาเปิด Session ก่อนสร้างออเดอร์'
                ))
        return orders

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.partner_id:
            self.customer_name = self.partner_id.name
            self.partner_phone = self.partner_id.phone or self.partner_id.mobile
            self.partner_address = self.partner_id.street
            self.partner_tax_id = self.partner_id.vat
            self.partner_invoice_id = self.partner_id.address_get(['invoice']).get('invoice', self.partner_id.id)
            self.partner_shipping_id = self.partner_id.address_get(['delivery']).get('delivery', self.partner_id.id)
            if getattr(self.partner_id, 'property_product_pricelist', False):
                self.pricelist_id = self.partner_id.property_product_pricelist
        else:
            self.customer_name = False
            self.partner_phone = False
            self.partner_address = False
            self.partner_tax_id = False
            self.partner_invoice_id = False
            self.partner_shipping_id = False

    @api.onchange('channel')
    def _onchange_channel(self):
        """Auto-map trade_channel from POS channel when not explicitly chosen."""
        if self.channel and not self.trade_channel:
            mapped = POS_CHANNEL_TO_TRADE_CHANNEL.get(self.channel)
            if mapped:
                self.trade_channel = mapped

    @api.onchange('session_id')
    def _onchange_session_id(self):
        if self.session_id:
            employees = self.session_id.employee_ids
            if self.session_id.employee_id and self.session_id.employee_id not in employees:
                employees |= self.session_id.employee_id
            if self.employee_id and self.employee_id not in employees:
                self.employee_id = False
            if not self.employee_id and self.session_id.employee_id:
                self.employee_id = self.session_id.employee_id
            return {'domain': {'employee_id': [('id', 'in', employees.ids)]}}
        return {'domain': {'employee_id': [('company_id', '=', self.company_id.id)]}}

    @api.onchange('company_id')
    def _onchange_company_id(self):
        if self.warehouse_id and self.pricelist_id:
            return  # already set from wizard context, don't overwrite
        config = self.env['pos.lite.config'].get_default_config(self.company_id)
        if config:
            self.warehouse_id = config.warehouse_id
            self.pricelist_id = config.pricelist_id

    #  Helpers ────────────────────────────────────────────────

    def _get_walk_in_partner(self):
        self.ensure_one()
        partner = self.env['res.partner'].search([
            ('name', '=', WALK_IN_CUSTOMER_NAME),
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        if not partner:
            partner = self.env['res.partner'].create({
                'name': WALK_IN_CUSTOMER_NAME,
                'company_id': self.company_id.id,
                'customer_rank': 1,
            })
        return partner

    def _get_or_create_customer_partner(self):
        self.ensure_one()
        if self.partner_id:
            return self.partner_id
        name = self.customer_name or WALK_IN_CUSTOMER_NAME
        partner = self.env['res.partner'].search([
            ('name', '=', name),
            ('company_id', 'in', [False, self.company_id.id]),
        ], limit=1)
        if not partner and self.partner_phone:
            partner = self.env['res.partner'].search([
                ('phone', '=', self.partner_phone),
                ('company_id', 'in', [False, self.company_id.id]),
            ], limit=1)
        if not partner:
            is_walkin = (name == WALK_IN_CUSTOMER_NAME)
            partner = self.env['res.partner'].create({
                'name': name,
                # Walk-in customer stays shared; named customers are company-scoped
                # so multi-company isolation and partner record rules hold.
                'company_id': False if is_walkin else self.company_id.id,
                'customer_rank': 1,
                'phone': self.partner_phone,
                'vat': self.partner_tax_id,
            })
        return partner

    def _get_default_payment_journal(self):
        self.ensure_one()
        config = self.env['pos.lite.config'].get_default_config(self.company_id)
        if config and config.journal_id:
            return config.journal_id
        return self.env['account.journal'].search([
            ('company_id', '=', self.company_id.id),
            ('type', 'in', ('cash', 'bank')),
        ], order='sequence, id', limit=1)

    # ─── Invoice / Picking preparation ─────────────────────────

    def _prepare_invoice_vals(self):
        self.ensure_one()
        partner = self._get_or_create_customer_partner()
        journal = self.env['account.journal'].search([
            ('company_id', '=', self.company_id.id),
            ('type', '=', 'sale'),
        ], limit=1)
        if not journal:
            raise UserError(_('No sales journal found for company %s.') % self.company_id.display_name)
        line_vals = []
        for line in self.line_ids:
            taxes = line.product_id.taxes_id.filtered(lambda t: t.company_id in (False, self.company_id))
            inv_price_unit = line.price_unit
            inv_discount = line.discount
            if line.discount_type == 'fixed':
                inv_price_unit = max(line.price_unit - line.discount, 0.0)
                inv_discount = 0.0
            line_vals.append(fields.Command.create({
                'product_id': line.product_id.id,
                'name': line.description or line.product_id.display_name,
                'quantity': line.qty,
                'price_unit': inv_price_unit,
                'discount': inv_discount,
                'tax_ids': [fields.Command.set(taxes.ids)],
                'product_uom_id': line.product_id.uom_id.id,
            }))
        invoice_partner = self.partner_invoice_id or partner
        vals = {
            'move_type': 'out_refund' if self.is_return else 'out_invoice',
            'company_id': self.company_id.id,
            'partner_id': invoice_partner.id,
            'partner_shipping_id': (self.partner_shipping_id or invoice_partner).id,
            'invoice_origin': self.name,
            'invoice_payment_term_id': False,
            'journal_id': journal.id,
            'trade_channel': self.trade_channel,
            'invoice_line_ids': line_vals,
        }
        # Link refund to the original posted invoice so reconciliation/etax
        # matching follows the chain (Thai e-tax downstream).
        if self.is_return and self.return_of_order_id.invoice_id:
            original = self.return_of_order_id.invoice_id
            if original.state == 'posted':
                vals['reversed_entry_id'] = original.id
        return vals

    def _prepare_picking_vals(self):
        self.ensure_one()
        partner = self._get_or_create_customer_partner()
        # Resolve picking type: config override → warehouse default
        config = self.env['pos.lite.config'].get_default_config(self.company_id)
        if self.is_return:
            picking_type = (
                config.return_picking_type_id
                if config and config.return_picking_type_id
                else self.warehouse_id.in_type_id
            )
            if not picking_type:
                raise UserError(_('No incoming picking type for warehouse %s.') % self.warehouse_id.display_name)
        else:
            picking_type = (
                config.out_picking_type_id
                if config and config.out_picking_type_id
                else self.warehouse_id.out_type_id
            )
            if not picking_type:
                raise UserError(_('No outgoing picking type for warehouse %s.') % self.warehouse_id.display_name)
        customer_location = self.env.ref('stock.stock_location_customers', raise_if_not_found=False)
        if not customer_location:
            customer_location = self.env['stock.location'].search([('usage', '=', 'customer')], limit=1)
        if not customer_location:
            raise UserError(_('No customer location found for stock delivery.'))
        moves = []
        for line in self.line_ids.filtered(lambda l: l.product_id.type != 'service' and l.qty > 0):
            location_id = customer_location.id if self.is_return else self.warehouse_id.lot_stock_id.id
            location_dest_id = self.warehouse_id.lot_stock_id.id if self.is_return else customer_location.id
            moves.append(fields.Command.create({
                'name': line.description or line.product_id.display_name,
                'product_id': line.product_id.id,
                'product_uom_qty': line.qty,
                'product_uom': line.product_id.uom_id.id,
                'location_id': location_id,
                'location_dest_id': location_dest_id,
            }))
        return {
            'picking_type_id': picking_type.id,
            'partner_id': (self.partner_shipping_id or partner).id,
            'origin': self.name,
            'company_id': self.company_id.id,
            'location_id': self.warehouse_id.lot_stock_id.id if not self.is_return else customer_location.id,
            'location_dest_id': customer_location.id if not self.is_return else self.warehouse_id.lot_stock_id.id,
            'move_ids_without_package': moves,
        }

    def _process_stock_picking(self, picking):
        picking.action_confirm()
        picking.action_assign()
        # Products tracked by lot/serial must be assigned manually — auto-filling
        # whatever Odoo reserved would silently mis-assign lots.
        tracked = picking.move_ids_without_package.filtered(
            lambda m: m.product_id.tracking != 'none'
        )
        if tracked:
            tracked_names = ', '.join(
                '%s (%s)' % (m.product_id.display_name, m.product_id.tracking)
                for m in tracked[:5]
            )
            raise UserError(_(
                'Order %s has lot/serial-tracked products (%s). '
                'Open the picking %s and select lots manually before validating.'
            ) % (picking.origin or picking.name, tracked_names, picking.name))
        for move in picking.move_ids_without_package:
            for move_line in move.move_line_ids:
                done_qty = move.product_uom_qty
                move_line.quantity = done_qty
            if not move.move_line_ids:
                move._action_assign()
        result = picking.button_validate()
        if isinstance(result, dict) and result.get('res_model') == 'stock.immediate.transfer':
            wizard = self.env['stock.immediate.transfer'].with_context(result.get('context', {})).create({
                'pick_ids': [fields.Command.set(picking.ids)],
            })
            wizard.process()
        elif isinstance(result, dict) and result.get('res_model') == 'stock.backorder.confirmation':
            wizard = self.env['stock.backorder.confirmation'].with_context(result.get('context', {})).create({})
            wizard.process_cancel_backorder()

    # ─── Actions: Flow ──────────────────────────────────────────


    def action_hold(self):
        """Hold order for later — can be resumed."""
        for order in self:
            if order.state != 'draft':
                raise UserError(_('Only draft orders can be held.'))
        self.write({'state': 'held'})

    def action_resume(self):
        """Resume a held order back to draft."""
        for order in self:
            if order.state != 'held':
                raise UserError(_('Only held orders can be resumed.'))
        self.write({'state': 'draft'})

    def action_quick_pay_and_process(self):
        """Process order: post invoice + validate picking. No payment registration."""
        self.ensure_one()
        if self.state not in ('draft', 'held'):
            raise UserError(_('Only draft or held orders can be processed.'))
        if not self.line_ids:
            raise UserError(_('Please add at least one order line.'))
        if self.state == 'held':
            self.write({'state': 'draft'})
        self.action_process_order()
        return True

    def action_process_order(self):
        skipped = []
        for order in self:
            if order.state not in ('draft',):
                skipped.append('%s (%s)' % (order.name or order.id, order.state))
                continue
            # Per-order savepoint: if picking validate or reconciliation raises,
            # we roll back so the order isn't left with a posted invoice but no
            # picking / half-reconciled payments.
            with self.env.cr.savepoint():
                order._process_one_order()
        # Non-draft orders were skipped silently before — now surfaced via the
        # chatter notification so the user knows not every selection was processed.
        if skipped:
            _logger.info('action_process_order skipped non-draft: %s', ', '.join(skipped))
        return True

    def _process_one_order(self):
        """Single-order body of action_process_order, wrapped in a savepoint by the caller."""
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_('Please add at least one order line.'))
        # Stock check (skip service + returns)
        if not self.is_return:
            for line in self.line_ids.filtered(lambda l: l.product_id.type != 'service'):
                if line.qty_available < line.qty:
                    raise UserError(
                        _('Insufficient stock for "%s": available %s, requested %s.')
                        % (line.product_id.display_name, line.qty_available, line.qty)
                    )
        # Ensure partner
        if not self.partner_id:
            self.partner_id = self._get_or_create_customer_partner().id
        # Create invoice
        if not self.invoice_id:
            invoice = self.env['account.move'].create(self._prepare_invoice_vals())
            invoice.action_post()
            self.invoice_id = invoice.id
        # Create picking
        if not self.picking_id:
            picking_vals = self._prepare_picking_vals()
            if picking_vals.get('move_ids_without_package'):
                picking = self.env['stock.picking'].create(picking_vals)
                self.picking_id = picking.id
                self._process_stock_picking(picking)
        # Invoice is posted only — no account.payment creation, no reconciliation.
        # pos.lite.payment rows stay as internal records; accounting settles separately.
        self.state = 'paid'
        # Auto-done if picking done (or no shippable products)
        has_shippable = any(l.product_id.type != 'service' for l in self.line_ids)
        picking_done = not has_shippable or (self.picking_id and self.picking_id.state == 'done')
        if picking_done:
            self.state = 'done'

    def action_done(self):
        """Manually mark done — only needed if auto-done didn't trigger (e.g. partial picking)."""
        for order in self:
            if order.state != 'paid':
                raise UserError(_('Only paid orders can be marked as done.'))
            has_shippable = any(l.product_id.type != 'service' for l in order.line_ids)
            if has_shippable and order.picking_id and order.picking_id.state != 'done':
                raise UserError(_('Stock picking must be completed first.'))
        self.write({'state': 'done'})

    def action_cancel(self):
        # Symmetry note: return orders (out_refund credit notes + incoming
        # pickings) auto-reverse on cancel because refunds are themselves the
        # "reversal" document. Sales with posted invoices / done pickings
        # refuse — the user must create a return so the original stays auditable.
        for order in self:
            # Reverse/unlink invoice
            if order.invoice_id and order.invoice_id.state == 'posted':
                if order.is_return:
                    reverse_wizard = self.env['account.move.reversal'].with_context(
                        active_model='account.move', active_ids=order.invoice_id.ids,
                    ).create({
                        'journal_id': order.invoice_id.journal_id.id,
                        'reason': _('Cancellation of return order %s') % order.name,
                    })
                    reverse_wizard.reverse_moves()
                    order.invoice_id = False
                else:
                    raise UserError(
                        _('Cannot cancel with a posted invoice. Create a return/refund instead.')
                    )
            # Reverse/unlink picking
            if order.picking_id and order.picking_id.state == 'done':
                if order.is_return:
                    # Use Odoo's stock.return.picking for safe reversal
                    return_wizard = self.env['stock.return.picking'].with_context(
                        active_id=order.picking_id.id,
                        active_model='stock.picking',
                    ).create({})
                    return_wizard._onchange_picking_id()
                    return_result = return_wizard._create_returns()
                    if return_result:
                        reverse_picking = self.env['stock.picking'].browse(return_result[0])
                        reverse_picking.action_confirm()
                        reverse_picking.action_assign()
                        for move in reverse_picking.move_ids_without_package:
                            for ml in move.move_line_ids:
                                ml.quantity = ml.reserved_uom_qty or move.product_uom_qty
                            if not move.move_line_ids:
                                move._action_assign()
                        validate_result = reverse_picking.button_validate()
                        if isinstance(validate_result, dict):
                            if validate_result.get('res_model') == 'stock.immediate.transfer':
                                self.env['stock.immediate.transfer'].with_context(
                                    validate_result.get('context', {})
                                ).create({'pick_ids': [fields.Command.set(reverse_picking.ids)]}).process()
                            elif validate_result.get('res_model') == 'stock.backorder.confirmation':
                                self.env['stock.backorder.confirmation'].with_context(
                                    validate_result.get('context', {})
                                ).create({}).process_cancel_backorder()
                    order.picking_id = False
                else:
                    raise UserError(
                        _('Cannot cancel with completed stock transfer. Create a return instead.')
                    )
            # Unlink draft invoice
            if order.invoice_id and order.invoice_id.state != 'posted':
                order.invoice_id.unlink()
                order.invoice_id = False
            # Cancel draft picking
            if order.picking_id and order.picking_id.state not in ('done', 'cancel'):
                order.picking_id.action_cancel()
                order.picking_id = False
            # Cancel account payments
            for pay in order.payment_ids:
                if pay.account_payment_id and pay.account_payment_id.state == 'posted':
                    pay.account_payment_id.action_cancel()
            order.payment_ids.unlink()
        self.write({'state': 'cancelled'})

    # ─── Actions: Return / Exchange ─────────────────────────────

    def action_create_return(self):
        self.ensure_one()
        if self.state != 'done':
            raise UserError(_('Only completed orders can be returned.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Create Return'),
            'res_model': 'pos.lite.return.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_order_id': self.id},
        }

    def action_create_exchange(self):
        self.ensure_one()
        if self.state != 'done':
            raise UserError(_('Only completed orders can be exchanged.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Exchange'),
            'res_model': 'pos.lite.return.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_order_id': self.id, 'default_is_exchange': True},
        }

    def action_view_returns(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Return Orders'),
            'res_model': 'pos.lite.order',
            'view_mode': 'tree,form',
            'domain': [('return_of_order_id', '=', self.id)],
            'target': 'current',
        }

    def action_view_exchanges(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Exchange Orders'),
            'res_model': 'pos.lite.order',
            'view_mode': 'tree,form',
            'domain': [('exchange_of_order_id', '=', self.id)],
            'target': 'current',
        }

    def action_reorder(self):
        self.ensure_one()
        if self.state not in ('paid', 'done', 'cancelled'):
            raise UserError(_('Only processed or cancelled orders can be re-ordered.'))
        line_commands = [fields.Command.create({
            'product_id': l.product_id.id,
            'description': l.description,
            'qty': l.qty,
            'price_unit': l.price_unit,
            'discount': l.discount,
        }) for l in self.line_ids]
        new_order = self.create({
            'company_id': self.company_id.id,
            'channel': self.channel,
            'trade_channel': self.trade_channel,
            'customer_name': self.customer_name,
            'partner_id': self.partner_id.id if self.partner_id else False,
            'partner_phone': self.partner_phone,
            'partner_invoice_id': self.partner_invoice_id.id if self.partner_invoice_id else False,
            'partner_shipping_id': self.partner_shipping_id.id if self.partner_shipping_id else False,
            'partner_tax_id': self.partner_tax_id,
            'warehouse_id': self.warehouse_id.id,
            'pricelist_id': self.pricelist_id.id,
            'note': _('Re-order from %s') % self.name,
            'line_ids': line_commands,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Re-order'),
            'res_model': 'pos.lite.order',
            'view_mode': 'form',
            'res_id': new_order.id,
            'target': 'current',
        }

    # ─── Actions: View linked docs ──────────────────────────────

    def action_view_invoice(self):
        self.ensure_one()
        if not self.invoice_id:
            raise UserError(_('No invoice created yet.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Credit Note') if self.is_return else _('Invoice'),
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.invoice_id.id,
            'target': 'current',
        }

    def action_view_picking(self):
        self.ensure_one()
        if not self.picking_id:
            raise UserError(_('No stock picking created yet.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Delivery Order'),
            'res_model': 'stock.picking',
            'view_mode': 'form',
            'res_id': self.picking_id.id,
            'target': 'current',
        }

    def action_view_payments(self):
        self.ensure_one()
        payments = self.payment_ids.mapped('account_payment_id')
        if not payments:
            raise UserError(_('No journal payments created yet.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Payments'),
            'res_model': 'account.payment',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', payments.ids)],
            'target': 'current',
        }

    # ─── Actions: Print ─────────────────────────────────────────

    def action_print_receipt_58mm(self):
        self.ensure_one()
        return self.env.ref('pos_lite.action_report_pos_lite_receipt_58mm').report_action(self)

    def action_print_receipt_80mm(self):
        self.ensure_one()
        return self.env.ref('pos_lite.action_report_pos_lite_receipt_80mm').report_action(self)

    def action_print_receipt_a4(self):
        self.ensure_one()
        return self.env.ref('pos_lite.action_report_pos_lite_receipt_a4').report_action(self)

    def action_print_pos_receipt(self):
        self.ensure_one()
        if not self.invoice_id:
            raise UserError(_('No invoice yet. Process the order first.'))
        return self.env.ref('buz_custom_invoice.action_report_pos_invoice_tax').report_action(self.invoice_id)

    def action_print_invoice(self):
        self.ensure_one()
        return self.env.ref('pos_lite.action_report_pos_lite_invoice').report_action(self)

    # ─── Migration ──────────────────────────────────────────────

    def _migration_fix_return_session_id(self):
        """Patch return/exchange orders created without session_id (pre-v17.0.3.5.0)."""
        self.env.cr.execute("""
            UPDATE pos_lite_order o
            SET session_id = orig.session_id
            FROM pos_lite_order orig
            WHERE o.is_return = TRUE
              AND o.session_id IS NULL
              AND o.return_of_order_id = orig.id
              AND orig.session_id IS NOT NULL
        """)
        rc = self.env.cr.rowcount
        self.env.cr.execute("""
            UPDATE pos_lite_order o
            SET session_id = orig.session_id
            FROM pos_lite_order orig
            WHERE o.is_exchange = TRUE
              AND o.session_id IS NULL
              AND o.exchange_of_order_id = orig.id
              AND orig.session_id IS NOT NULL
        """)
        ec = self.env.cr.rowcount
        if rc or ec:
            _logger.info('POS Lite migration: fixed session_id for %d return and %d exchange orders', rc, ec)


# ═══════════════════════════════════════════════════════════════
# Order Line
# ═══════════════════════════════════════════════════════════════

class PosLiteOrderLine(models.Model):
    _name = 'pos.lite.order.line'
    _description = 'POS Lite Order Line'
    _order = 'id asc'

    order_id = fields.Many2one('pos.lite.order', required=True, ondelete='cascade', check_company=True)
    company_id = fields.Many2one(related='order_id.company_id', store=True, readonly=True)
    currency_id = fields.Many2one(related='order_id.currency_id', store=True, readonly=True)
    product_id = fields.Many2one('product.product', required=True, domain="[('sale_ok', '=', True)]", check_company=True)
    product_image = fields.Binary(
        related='product_id.image_128', string='Image',
        readonly=True, store=False,
    )
    description = fields.Char()
    qty = fields.Float(default=1.0)
    price_unit = fields.Monetary(required=True)
    discount = fields.Float(default=0.0)
    discount_type = fields.Selection([
        ('percent', 'Percent'),
        ('fixed', 'Fixed'),
    ], default='fixed', string='Discount Type', required=True)
    returned_from_line_id = fields.Many2one('pos.lite.order.line', copy=False, index=True)
    return_line_ids = fields.One2many('pos.lite.order.line', 'returned_from_line_id', string='Return Lines')
    returned_qty = fields.Float(compute='_compute_returned_qty', store=False)
    available_return_qty = fields.Float(compute='_compute_returned_qty', store=False)
    qty_available = fields.Float(compute='_compute_qty_available', string='On Hand')
    is_low_stock = fields.Boolean(compute='_compute_qty_available', string='Low Stock')
    price_subtotal = fields.Monetary(compute='_compute_amounts', store=True)
    price_tax = fields.Monetary(compute='_compute_amounts', store=True)
    price_total = fields.Monetary(compute='_compute_amounts', store=True)
    standard_cost_price = fields.Float(
        string="Standard Cost",
        compute='_compute_standard_cost_margin',
        store=True,
        digits='Product Price',
        help="Per-unit standard cost pulled from the company's Standard Cost "
             "Pricelist (same source and method as sale.order.line).",
    )
    margin = fields.Monetary(
        string="Margin",
        compute='_compute_standard_cost_margin',
        store=True,
        currency_field='currency_id',
        help="Line margin = price subtotal − (standard cost × qty).",
    )

    @api.depends('return_line_ids.qty')
    def _compute_returned_qty(self):
        for line in self:
            returned_qty = sum(line.return_line_ids.mapped('qty'))
            line.returned_qty = returned_qty
            line.available_return_qty = max(line.qty - returned_qty, 0.0)

    @api.depends('product_id', 'qty', 'order_id.warehouse_id')
    def _compute_qty_available(self):
        # Batch: collect all (product_id, warehouse.lot_stock_id) pairs
        lines_by_key = {}
        for line in self:
            product = line.product_id
            if not product or product.type == 'service':
                line.qty_available = 0.0
                line.is_low_stock = False
                continue
            warehouse = line.order_id.warehouse_id
            if not warehouse:
                line.qty_available = 0.0
                line.is_low_stock = False
                continue
            key = (product.id, warehouse.lot_stock_id.id)
            lines_by_key.setdefault(key, []).append(line)

        if not lines_by_key:
            return

        product_ids = list({k[0] for k in lines_by_key})
        location_ids = list({k[1] for k in lines_by_key})
        quant_data = self.env['stock.quant'].read_group(
            domain=[
                ('product_id', 'in', product_ids),
                ('location_id', 'in', location_ids),
            ],
            fields=['quantity:sum'],
            groupby=['product_id', 'location_id'],
            lazy=False,
        )
        qty_map = {}
        for q in quant_data:
            pid = q['product_id'][0] if isinstance(q['product_id'], (list, tuple)) else q['product_id']
            lid = q['location_id'][0] if isinstance(q['location_id'], (list, tuple)) else q['location_id']
            qty_map[(pid, lid)] = q['quantity']

        for key, lines in lines_by_key.items():
            on_hand = qty_map.get(key, 0.0)
            for line in lines:
                line.qty_available = on_hand
                line.is_low_stock = on_hand < line.qty

    @api.depends('qty', 'price_unit', 'discount', 'discount_type', 'product_id', 'order_id.partner_id', 'order_id.pricelist_id')
    def _compute_amounts(self):
        for line in self:
            price = line.price_unit or 0.0
            if line.discount_type == 'fixed':
                discounted = max(price - (line.discount or 0.0), 0.0)
            else:
                discounted = price * (1.0 - (line.discount or 0.0) / 100.0)
            taxes = line.product_id.taxes_id.filtered(lambda t: t.company_id in (False, line.company_id))
            if taxes:
                tax_res = taxes.compute_all(
                    discounted, currency=line.currency_id,
                    quantity=line.qty or 1.0,
                    product=line.product_id,
                    partner=line.order_id.partner_id,
                )
                line.price_subtotal = tax_res['total_excluded']
                line.price_tax = tax_res['total_included'] - tax_res['total_excluded']
                line.price_total = tax_res['total_included']
            else:
                subtotal = discounted * (line.qty or 1.0)
                line.price_subtotal = subtotal
                line.price_tax = 0.0
                line.price_total = subtotal

    @api.depends('product_id', 'qty', 'price_subtotal', 'currency_id', 'company_id',
                 'order_id.date_order', 'order_id.company_id')
    def _compute_standard_cost_margin(self):
        # Pulls the standard cost from the same Standard Cost Pricelist (and the
        # same helper) used by sale.order.line, so POS Lite margin == SO margin.
        # standard_cost_price is per-unit (priced at qty=1); line margin spreads
        # it over the line qty, exactly like sale_margin's
        # price_subtotal − (purchase_price × product_uom_qty).
        pricelists = {}
        Pricelist = self.env['product.pricelist']
        for line in self:
            if not line.product_id or not line.order_id:
                line.standard_cost_price = 0.0
                line.margin = 0.0
                continue

            company = line.company_id or line.order_id.company_id
            cid = company.id
            if cid not in pricelists:
                pricelists[cid] = Pricelist._get_standard_cost_pricelist(company)
            pricelist = pricelists[cid]

            if not pricelist:
                line.standard_cost_price = 0.0
                line.margin = 0.0
                continue

            date_order = line.order_id.date_order or fields.Date.today()
            cost_price = pricelist._get_product_standard_cost_price(
                line.product_id, line.currency_id,
                company=company, date=date_order,
            )
            line.standard_cost_price = cost_price
            line.margin = line.price_subtotal - (cost_price * (line.qty or 0.0))

    @api.onchange('product_id', 'qty', 'order_id.pricelist_id', 'order_id.partner_id')
    def _onchange_product_id(self):
        for line in self:
            if not line.product_id:
                line.description = False
                continue
            line.description = line.product_id.display_name
            line.qty = line.qty or 1.0
            pricelist = line.order_id.pricelist_id
            partner = line.order_id.partner_id
            price = line.product_id.lst_price
            if pricelist:
                try:
                    if hasattr(pricelist, '_get_product_price'):
                        price = pricelist._get_product_price(line.product_id, line.qty or 1.0, partner)
                    else:
                        price = pricelist._get_product_price_rule(line.product_id, line.qty or 1.0, partner)[0]
                except (AttributeError, IndexError, TypeError):
                    _logger.warning(
                        'Pricelist %s failed for %s; falling back to lst_price',
                        pricelist.id, line.product_id.display_name, exc_info=True,
                    )
                    price = line.product_id.lst_price
            line.price_unit = price
            if line.discount is None:
                line.discount = 0.0
            if not line.discount_type:
                line.discount_type = 'fixed'
            if not line.discount_type:
                line.discount_type = 'fixed'

    @api.constrains('qty', 'price_unit', 'discount', 'discount_type')
    def _check_values(self):
        for line in self:
            if line.qty <= 0:
                raise ValidationError(_('Quantity must be greater than zero.'))
            if line.discount < 0:
                raise ValidationError(_('Discount must be a positive number.'))
            if line.discount_type == 'percent' and line.discount > 100:
                raise ValidationError(_('Percent discount must be between 0 and 100.'))
            if line.discount_type == 'fixed' and line.discount > line.price_unit:
                raise ValidationError(_('Fixed discount cannot exceed unit price.'))
