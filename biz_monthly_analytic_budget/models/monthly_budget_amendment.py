# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class MonthlyBudgetAmendment(models.Model):
    """
    Audit log for budget plan changes.

    Every time the total_budget or a budget line allocation is changed,
    a record is created here capturing the before/after snapshot and
    the reason for the change.
    """
    _name = 'monthly.budget.amendment'
    _description = 'Monthly Budget Amendment'
    _order = 'date desc, id desc'
    _inherit = ['mail.thread']

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
    )
    plan_id = fields.Many2one(
        'monthly.budget.plan',
        string='Budget Plan',
        required=True,
        ondelete='cascade',
        index=True,
    )
    budget_line_id = fields.Many2one(
        'monthly.budget.line',
        string='Budget Line',
        ondelete='set null',
        help='If set, this amendment applies to a specific line. If blank, it applies to the plan total.',
    )
    amendment_type = fields.Selection(
        selection=[
            ('increase', 'Increase'),
            ('decrease', 'Decrease'),
            ('reallocation', 'Reallocation'),
        ],
        string='Type',
        required=True,
    )
    amount_before = fields.Monetary(
        string='Amount Before',
        currency_field='currency_id',
        required=True,
    )
    amount_change = fields.Monetary(
        string='Change (+/-)',
        currency_field='currency_id',
        required=True,
    )
    amount_after = fields.Monetary(
        string='Amount After',
        currency_field='currency_id',
        required=True,
    )
    currency_id = fields.Many2one(
        related='plan_id.currency_id',
        readonly=True,
        store=True,
    )
    reason = fields.Text(
        string='Reason',
        required=True,
        help='Reason for the budget amendment',
    )
    user_id = fields.Many2one(
        'res.users',
        string='Changed By',
        default=lambda self: self.env.uid,
        readonly=True,
    )
    date = fields.Datetime(
        string='Date',
        default=fields.Datetime.now,
        readonly=True,
    )
    company_id = fields.Many2one(
        related='plan_id.company_id',
        store=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'monthly.budget.amendment'
                ) or _('New')
        return super().create(vals_list)
