# -*- coding: utf-8 -*-
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
        'hr.employee', string='Employee', required=True,
        default=lambda self: self._default_employee_id(),
        tracking=True, check_company=True,
        domain="[('company_id', '=', company_id)]",
    )
    close_user_id = fields.Many2one('res.users', readonly=True, string='Closed By')
    order_ids = fields.One2many('pos.lite.order', 'session_id', string='Orders')
    order_count = fields.Integer(compute='_compute_stats', string='Orders')
    order_count_sales = fields.Integer(compute='_compute_stats', string='Sales Orders')
    order_count_returns = fields.Integer(compute='_compute_stats', string='Returns')
    amount_total = fields.Monetary(compute='_compute_stats', string='Total Sales')
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

    @api.depends('order_ids.state', 'order_ids.amount_total', 'order_ids.is_return')
    def _compute_stats(self):
        for session in self:
            done_orders = session.order_ids.filtered(lambda o: o.state in ('paid', 'done'))
            sales = done_orders.filtered(lambda o: not o.is_return)
            returns = done_orders.filtered(lambda o: o.is_return)
            session.order_count = len(done_orders)
            session.order_count_sales = len(sales)
            session.order_count_returns = len(returns)
            session.amount_total = sum(sales.mapped('amount_total'))
            session.amount_untaxed = sum(sales.mapped('amount_untaxed'))
            session.amount_tax = sum(sales.mapped('amount_tax'))
            session.amount_refund = sum(returns.mapped('amount_total'))
            session.amount_net = session.amount_total - session.amount_refund

    @api.depends('order_ids.payment_ids')
    def _compute_payment_breakdown(self):
        for session in self:
            payments = session.order_ids.filtered(
                lambda o: o.state in ('paid', 'done') and not o.is_return
            ).mapped('payment_ids')
            session.payment_cash = sum(p.amount for p in payments if p.payment_method == 'cash' and p.amount > 0)
            session.payment_transfer = sum(p.amount for p in payments if p.payment_method == 'transfer' and p.amount > 0)
            session.payment_card = sum(p.amount for p in payments if p.payment_method == 'card' and p.amount > 0)
            session.payment_promptpay = sum(p.amount for p in payments if p.payment_method == 'promptpay' and p.amount > 0)
            session.payment_other = sum(p.amount for p in payments if p.payment_method == 'other' and p.amount > 0)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/' or not vals.get('name'):
                vals['name'] = self.env['ir.sequence'].next_by_code('pos.lite.session') or '/'
        return super().create(vals_list)

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
            # Check if there's already an open session for this company
            existing = self.search([
                ('company_id', '=', session.company_id.id),
                ('state', '=', 'opened'),
            ], limit=1)
            if existing:
                raise UserError(
                    _('Session %s is already open. Close it first before reopening.') % existing.name
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
