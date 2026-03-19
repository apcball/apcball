# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ArSettlementCreditLine(models.Model):
    _name = 'ar.settlement.credit.line'
    _description = 'AR Settlement Credit Note Line'

    settlement_id = fields.Many2one(
        'ar.settlement', string='Settlement',
        required=True, ondelete='cascade',
    )
    credit_move_id = fields.Many2one(
        'account.move', string='Credit Note', required=True,
        domain=[
            ('state', '=', 'posted'),
            ('move_type', '=', 'out_refund'),
            ('payment_state', 'in', ['not_paid', 'partial']),
        ],
    )
    partner_id = fields.Many2one(
        'res.partner', string='Branch',
        related='credit_move_id.partner_id', readonly=True,
    )
    currency_id = fields.Many2one(
        'res.currency', related='credit_move_id.currency_id', readonly=True,
    )
    credit_total = fields.Monetary(
        string='Total',
        related='credit_move_id.amount_total', readonly=True,
        currency_field='currency_id',
    )
    credit_residual = fields.Monetary(
        string='Residual', compute='_compute_credit_residual',
        currency_field='currency_id',
    )
    selected = fields.Boolean(
        string='Select', default=False,
        help='Tick to apply this credit note in the settlement.',
    )
    use_amount = fields.Monetary(
        string='Use Amount', currency_field='currency_id',
    )

    @api.depends('credit_move_id', 'credit_move_id.amount_residual')
    def _compute_credit_residual(self):
        for line in self:
            line.credit_residual = abs(line.credit_move_id.amount_residual) if line.credit_move_id else 0.0

    @api.constrains('use_amount', 'credit_residual')
    def _check_use_amount(self):
        for line in self:
            if line.use_amount < 0:
                raise ValidationError(
                    _('Use amount cannot be negative for credit note %s.')
                    % line.credit_move_id.name
                )
            if line.use_amount > line.credit_residual:
                raise ValidationError(
                    _('Use amount (%.2f) cannot exceed residual (%.2f) for credit note %s.')
                    % (line.use_amount, line.credit_residual, line.credit_move_id.name)
                )
