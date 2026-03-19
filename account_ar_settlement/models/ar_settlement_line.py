# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ArSettlementLine(models.Model):
    _name = 'ar.settlement.line'
    _description = 'AR Settlement Invoice Line'

    settlement_id = fields.Many2one(
        'ar.settlement', string='Settlement',
        required=True, ondelete='cascade',
    )
    invoice_id = fields.Many2one(
        'account.move', string='Invoice', required=True,
        domain=[
            ('state', '=', 'posted'),
            ('move_type', '=', 'out_invoice'),
            ('payment_state', 'in', ['not_paid', 'partial']),
        ],
    )
    partner_id = fields.Many2one(
        'res.partner', string='Branch',
        related='invoice_id.partner_id', readonly=True,
    )
    trade_channel = fields.Char(
        string='Trade Channel',
        compute='_compute_trade_channel', readonly=True,
    )
    invoice_date = fields.Date(
        string='Invoice Date',
        related='invoice_id.invoice_date', readonly=True,
    )
    date_due = fields.Date(
        string='Due Date',
        related='invoice_id.invoice_date_due', readonly=True,
    )
    currency_id = fields.Many2one(
        'res.currency', related='invoice_id.currency_id', readonly=True,
    )
    residual = fields.Monetary(
        string='Residual',
        related='invoice_id.amount_residual', readonly=True,
        currency_field='currency_id',
    )
    selected = fields.Boolean(
        string='Select', default=False,
        help='Tick to include this invoice in the settlement.',
    )
    pay_amount = fields.Monetary(
        string='Pay Amount', currency_field='currency_id',
    )
    is_overdue = fields.Boolean(
        string='Overdue', compute='_compute_is_overdue',
    )

    @api.onchange('selected')
    def _onchange_selected(self):
        for line in self:
            if line.selected:
                # Auto-fill pay_amount = residual when ticking select
                line.pay_amount = line.residual or 0.0
            else:
                line.pay_amount = 0.0

    @api.onchange('invoice_id')
    def _onchange_invoice_id(self):
        """Auto-tick and fill pay_amount when invoice is chosen manually."""
        for line in self:
            if line.invoice_id:
                line.selected = True
                line.pay_amount = line.residual or 0.0
            else:
                line.selected = False
                line.pay_amount = 0.0

    @api.depends('invoice_id')
    def _compute_trade_channel(self):
        has_field = 'trade_channel' in self.env['account.move']._fields
        for line in self:
            if has_field and line.invoice_id:
                tc = line.invoice_id.trade_channel
                # trade_channel may be a selection key – get the label
                if tc:
                    selection = dict(
                        self.env['account.move']._fields['trade_channel'].selection
                    )
                    line.trade_channel = selection.get(tc, tc)
                else:
                    line.trade_channel = ''
            else:
                line.trade_channel = ''

    @api.depends('date_due')
    def _compute_is_overdue(self):
        today = fields.Date.context_today(self)
        for line in self:
            line.is_overdue = bool(line.date_due and line.date_due < today)

    @api.constrains('pay_amount', 'residual')
    def _check_pay_amount(self):
        for line in self:
            if line.pay_amount < 0:
                raise ValidationError(
                    _('Pay amount cannot be negative for invoice %s.')
                    % line.invoice_id.name
                )
            if line.pay_amount > line.residual:
                raise ValidationError(
                    _('Pay amount (%.2f) cannot exceed residual (%.2f) for invoice %s.')
                    % (line.pay_amount, line.residual, line.invoice_id.name)
                )
