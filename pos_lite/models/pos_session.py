from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PosLiteSession(models.Model):
    _name = 'pos.lite.session'
    _description = 'POS Lite Daily Session'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'
    _rec_name = 'name'

    name = fields.Char(default='/', copy=False, readonly=True, tracking=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id', store=True, readonly=True)
    config_id = fields.Many2one(
        'pos.lite.config', required=True,
        domain="[('company_id', '=', company_id)]",
        check_company=True,
    )
    location_id = fields.Many2one(
        'stock.location', related='config_id.location_id',
        store=True, readonly=True, string='Location',
        help='Stock location this session operates from, inherited from its '
             'configuration. Drives product availability and picking source.',
    )
    state = fields.Selection([
        ('opened', 'Opened'),
        ('closed', 'Closed'),
    ], default='opened', required=True, tracking=True)
    date_open = fields.Datetime(default=fields.Datetime.now, readonly=True, string='Open Date')
    date_close = fields.Datetime(readonly=True, string='Close Date')
    user_id = fields.Many2one(
        'res.users', default=lambda self: self.env.user,
        readonly=True, string='Opened By',
    )
    employee_id = fields.Many2one(
        'hr.employee', string='Primary Employee',
        default=lambda self: self._default_employee_id(),
        tracking=True, check_company=True,
        domain="[('company_id', '=', company_id)]",
    )
    employee_ids = fields.Many2many(
        'hr.employee', string='Employees',
        relation='pos_lite_session_hr_employee_rel',
        column1='session_id', column2='employee_id',
        default=lambda self: self._default_employee_ids(),
        tracking=True, check_company=True,
        domain="[('company_id', '=', company_id)]",
    )
    close_user_id = fields.Many2one('res.users', readonly=True, string='Closed By')
    order_ids = fields.One2many('pos.lite.order', 'session_id', string='Orders')
    order_count = fields.Integer(compute='_compute_stats', string='Orders')
    order_count_sales = fields.Integer(compute='_compute_stats', string='Regular Sales')
    order_count_exchanges = fields.Integer(compute='_compute_stats', string='Exchanges')
    order_count_returns = fields.Integer(compute='_compute_stats', string='Returns')
    amount_total = fields.Monetary(compute='_compute_stats', string='Total Sales')
    amount_regular_sales = fields.Monetary(compute='_compute_stats', string='Regular Sales Amount')
    amount_exchange_sales = fields.Monetary(compute='_compute_stats', string='Exchange Sales Amount')
    amount_tax = fields.Monetary(compute='_compute_stats', string='Total Tax')
    amount_untaxed = fields.Monetary(compute='_compute_stats', string='Total Untaxed')
    amount_refund = fields.Monetary(compute='_compute_stats', string='Total Refunds')
    amount_net = fields.Monetary(compute='_compute_stats', string='Net Revenue')
    # Payment breakdown
    payment_cash = fields.Monetary(compute='_compute_payment_breakdown', string='Cash')
    payment_transfer = fields.Monetary(compute='_compute_payment_breakdown', string='Transfer')
    payment_card = fields.Monetary(compute='_compute_payment_breakdown', string='Card')
    payment_promptpay = fields.Monetary(compute='_compute_payment_breakdown', string='PromptPay')
    payment_other = fields.Monetary(compute='_compute_payment_breakdown', string='Other')
    note = fields.Text()
    # Remember last sale selection per session
    current_employee_id = fields.Many2one(
        'hr.employee', string='พนักงานขายปัจจุบัน',
        tracking=True, check_company=True,
        domain="[('company_id', '=', company_id)]",
    )
    current_channel = fields.Selection([
        ('phone', 'Phone'),
        ('line', 'LINE'),
        ('walkin', 'Walk-in'),
        ('other', 'Other'),
    ], string='ช่องทางล่าสุด', tracking=True)
    current_trade_channel = fields.Selection(
        selection='_selection_trade_channel',
        string='Trade Channel ล่าสุด',
        help='Trade channel last used in this session for settlement grouping.',
        tracking=True,
    )

    @api.model
    def _selection_trade_channel(self):
        """Dynamic selection mirroring sale.order.trade_channel (injected by marketplace_settlement)."""
        from .pos_order import _get_trade_channel_selection
        return _get_trade_channel_selection(self)

    _sql_constraints = [
        ('name_unique', 'unique(name)', 'Session number must be unique.'),
    ]

    def _default_employee_id(self):
        employee = self.env['hr.employee'].search([
            ('user_id', '=', self.env.uid),
            ('company_id', 'in', self.env.companies.ids),
        ], limit=1)
        if not employee:
            config = self.env['pos.lite.config'].get_default_config()
            if config and config.employee_id:
                return config.employee_id
        return employee

    def _default_employee_ids(self):
        employee = self._default_employee_id()
        return employee and employee.ids or []

    @api.depends('order_ids.state', 'order_ids.amount_total', 'order_ids.is_return', 'order_ids.is_exchange')
    def _compute_stats(self):
        for session in self:
            done_orders = session.order_ids.filtered(lambda o: o.state in ('paid', 'done'))
            sales = done_orders.filtered(lambda o: not o.is_return)
            returns = done_orders.filtered(lambda o: o.is_return)
            exchanges = sales.filtered(lambda o: o.is_exchange)
            regular = sales.filtered(lambda o: not o.is_exchange)
            session.order_count = len(done_orders)
            session.order_count_sales = len(regular)
            session.order_count_exchanges = len(exchanges)
            session.order_count_returns = len(returns)
            session.amount_regular_sales = sum(regular.mapped('amount_total'))
            session.amount_exchange_sales = sum(exchanges.mapped('amount_total'))
            session.amount_total = sum(sales.mapped('amount_total'))
            session.amount_untaxed = sum(sales.mapped('amount_untaxed')) - abs(sum(returns.mapped('amount_untaxed')))
            session.amount_tax = sum(sales.mapped('amount_tax')) - abs(sum(returns.mapped('amount_tax')))
            session.amount_refund = abs(sum(returns.mapped('amount_total')))
            session.amount_net = session.amount_total - session.amount_refund

    @api.depends('order_ids.payment_ids', 'order_ids.payment_ids.amount', 'order_ids.payment_ids.payment_method', 'order_ids.state')
    def _compute_payment_breakdown(self):
        for session in self:
            done_orders = session.order_ids.filtered(lambda o: o.state in ('paid', 'done'))
            payments = done_orders.mapped('payment_ids')
            session.payment_cash = sum(p.amount for p in payments if p.payment_method == 'cash')
            session.payment_transfer = sum(p.amount for p in payments if p.payment_method == 'transfer')
            session.payment_card = sum(p.amount for p in payments if p.payment_method == 'card')
            session.payment_promptpay = sum(p.amount for p in payments if p.payment_method == 'promptpay')
            session.payment_other = sum(p.amount for p in payments if p.payment_method == 'other')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/' or not vals.get('name'):
                vals['name'] = self.env['ir.sequence']._safe_next_by_code(
                    'pos.lite.session', 'pos.lite.session', prefix='SESS',
                )
        sessions = super().create(vals_list)
        sessions._check_single_open_session()
        return sessions

    def _check_single_open_session(self):
        """At most one opened session per (company, location) — prevents ambiguous
        sales attribution when two shifts run simultaneously on the same location.

        Falls back to config_id when location_id is unset (legacy configs without
        a bound location) so the invariant still holds for those records."""
        for session in self:
            if session.state != 'opened':
                continue
            domain = [
                ('id', '!=', session.id),
                ('company_id', '=', session.company_id.id),
                ('state', '=', 'opened'),
            ]
            if session.location_id:
                domain.append(('location_id', '=', session.location_id.id))
            else:
                domain.append(('config_id', '=', session.config_id.id))
            existing = self.search(domain, limit=1)
            if existing:
                loc_label = session.location_id.display_name or session.config_id.display_name
                raise UserError(_(
                    'Session %s is already open for this location (%s). '
                    'Close it before opening a new one.'
                ) % (existing.name, loc_label))

    def action_close_session(self):
        for session in self:
            if session.state != 'opened':
                raise UserError(_('Session is already closed.'))
            # Check for draft orders
            draft_orders = session.order_ids.filtered(lambda o: o.state in ('draft', 'held'))
            if draft_orders:
                raise UserError(
                    _('Cannot close session with %d pending order(s). '
                      'Please process or cancel them first.') % len(draft_orders)
                )
            session.write({
                'state': 'closed',
                'date_close': fields.Datetime.now(),
                'close_user_id': self.env.user.id,
            })

    def action_reopen_session(self):
        for session in self:
            if session.state != 'closed':
                raise UserError(_('Only closed sessions can be reopened.'))
            # Check if there's already an open session for this location
            # (or config, for legacy configs without a bound location).
            domain = [
                ('company_id', '=', session.company_id.id),
                ('state', '=', 'opened'),
            ]
            if session.location_id:
                domain.append(('location_id', '=', session.location_id.id))
            else:
                domain.append(('config_id', '=', session.config_id.id))
            existing = self.search(domain, limit=1)
            if existing:
                loc_label = session.location_id.display_name or session.config_id.display_name
                raise UserError(
                    _('Session %s is already open for this location (%s). '
                      'Close it first before reopening.') % (existing.name, loc_label)
                )
            session.write({
                'state': 'opened',
                'date_close': False,
                'close_user_id': False,
            })

    def action_view_orders(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Session Orders'),
            'res_model': 'pos.lite.order',
            'view_mode': 'tree,form',
            'domain': [('session_id', '=', self.id)],
            'target': 'current',
        }

    def action_print_session_summary(self):
        self.ensure_one()
        return self.env.ref('pos_lite.action_report_pos_lite_session').report_action(self)

    def action_start_sale(self):
        """เปิด wizard เลือกพนักงานขาย — ครั้งแรกหรือต้องการเปลี่ยน"""
        self.ensure_one()
        if self.state != 'opened':
            raise UserError(_('Session must be opened to start selling.'))
        employees = self.employee_ids
        if self.employee_id and self.employee_id not in employees:
            employees |= self.employee_id
        if not employees:
            raise UserError(_('No employees assigned to this session. Please add employees first.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('เลือกพนักงานขาย'),
            'res_model': 'pos.lite.start.sale.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_session_id': self.id,
            },
        }

    def action_new_order(self):
        """สร้าง order ใหม่ — ใช้ค่าพนักงาน+ช่องทางที่จำไว้ใน session"""
        self.ensure_one()
        if self.state != 'opened':
            raise UserError(_('Session must be opened to create orders.'))
        if not self.current_employee_id:
            # ยังไม่เคยเลือก → เปิด wizard
            return self.action_start_sale()

        config = self.config_id
        ctx = {
            'default_session_id': self.id,
            'default_employee_id': self.current_employee_id.id,
            'default_channel': self.current_channel or 'walkin',
            'default_trade_channel': self.current_trade_channel or config.default_trade_channel or False,
            'default_company_id': self.company_id.id,
        }
        if config:
            ctx.update({
                'default_warehouse_id': config.warehouse_id.id,
                'default_pricelist_id': config.pricelist_id.id,
            })

        return {
            'type': 'ir.actions.act_window',
            'name': _('สั่งขาย — %s') % self.current_employee_id.name,
            'res_model': 'pos.lite.order',
            'view_mode': 'form',
            'target': 'current',
            'context': ctx,
        }

    def action_open_terminal(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'name': 'POS Lite Terminal',
            'url': '/pos_lite/ui?session_id=%d' % self.id,
            'target': 'new',
        }
