# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class RefillStockWizard(models.TransientModel):
    _name = 'buz.marketplace.refill.stock.wizard'
    _description = 'Refill Buffer Stock Wizard'

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

    def action_refill(self):
        success = 0
        errors = 0
        for product in self.marketplace_product_ids:
            try:
                product.action_refill()
                success += 1
            except Exception:
                errors += 1
        message = _('Refilled: %s, Errors: %s') % (success, errors)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Refill Complete'),
                'message': message,
                'type': 'success' if not errors else 'warning',
                'sticky': False,
            },
        }
