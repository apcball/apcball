# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class FetchStockWizard(models.TransientModel):
    _name = 'buz.marketplace.fetch.stock.wizard'
    _description = 'Fetch Stock from Marketplace Wizard'

    marketplace_product_ids = fields.Many2many('buz.marketplace.product',
        string='Marketplace Products', required=True)
    product_count = fields.Integer(string='Products Selected',
        compute='_compute_product_count')

    @api.depends('marketplace_product_ids')
    def _compute_product_count(self):
        for record in self:
            record.product_count = len(record.marketplace_product_ids)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_ids = self.env.context.get('active_ids')
        if active_ids:
            res['marketplace_product_ids'] = [(6, 0, active_ids)]
        return res

    def action_fetch_stock(self):
        for product in self.marketplace_product_ids:
            product.action_fetch_stock()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Stock Fetched'),
                'message': _('Updated stock for %s products') % self.product_count,
                'type': 'success',
                'sticky': False,
            },
        }
