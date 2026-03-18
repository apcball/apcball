# -*- coding: utf-8 -*-
from odoo import models, fields, api

class ResCurrencyRate(models.Model):
    _inherit = 'res.currency.rate'

    buy_rate = fields.Float(
        string="Buy Rate (Internal)",
        digits=(12, 6),
        help="Rate used when purchasing foreign currency (Odoo internal format: 1 / THB per unit)"
    )
    sell_rate = fields.Float(
        string="Sell Rate (Internal)",
        digits=(12, 6),
        help="Rate used when selling foreign currency (Odoo internal format: 1 / THB per unit)"
    )

    inverse_buy_rate = fields.Float(
        string="Buy Rate",
        digits=(12, 6),
        compute='_compute_inverse_buy_rate',
        inverse='_inverse_inverse_buy_rate',
        help="Rate used when purchasing foreign currency (e.g. 33.25 THB per USD)"
    )

    inverse_sell_rate = fields.Float(
        string="Sell Rate",
        digits=(12, 6),
        compute='_compute_inverse_sell_rate',
        inverse='_inverse_inverse_sell_rate',
        help="Rate used when selling foreign currency (e.g. 34.00 THB per USD)"
    )

    @api.depends('buy_rate')
    def _compute_inverse_buy_rate(self):
        for rate in self:
            rate.inverse_buy_rate = 1.0 / rate.buy_rate if rate.buy_rate else 0.0

    def _inverse_inverse_buy_rate(self):
        for rate in self:
            rate.buy_rate = 1.0 / rate.inverse_buy_rate if rate.inverse_buy_rate else 0.0

    @api.depends('sell_rate')
    def _compute_inverse_sell_rate(self):
        for rate in self:
            rate.inverse_sell_rate = 1.0 / rate.sell_rate if rate.sell_rate else 0.0

    def _inverse_inverse_sell_rate(self):
        for rate in self:
            rate.sell_rate = 1.0 / rate.inverse_sell_rate if rate.inverse_sell_rate else 0.0
