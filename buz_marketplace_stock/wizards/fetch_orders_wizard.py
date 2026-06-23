# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class FetchOrdersWizard(models.TransientModel):
    _name = 'buz.marketplace.fetch.orders.wizard'
    _description = 'Fetch Orders from Marketplace Wizard'

    account_id = fields.Many2one('buz.marketplace.account',
        string='Marketplace Account', required=True)
    lookback_minutes = fields.Integer(string='Lookback (minutes)',
        default=30, help='Fetch orders created in the last N minutes')
    auto_create_so = fields.Boolean(string='Auto-Create Sale Orders',
        default=True)

    def action_fetch_orders(self):
        self.ensure_one()
        account = self.account_id
        original_lookback = account.order_lookback_minutes
        account.order_lookback_minutes = self.lookback_minutes
        try:
            result = account.action_fetch_orders()
            return result
        finally:
            account.order_lookback_minutes = original_lookback
