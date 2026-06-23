# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    marketplace_sku = fields.Char(
        string='Marketplace SKU',
        help='SKU used on marketplace platforms (Shopee, Lazada)'
    )
    marketplace_product_count = fields.Integer(
        string='Marketplace Products',
        compute='_compute_marketplace_product_count'
    )

    @api.depends('product_variant_ids.marketplace_product_ids')
    def _compute_marketplace_product_count(self):
        for template in self:
            template.marketplace_product_count = self.env['buz.marketplace.product'].search_count([
                ('product_tmpl_id', '=', template.id)
            ])

    def action_view_marketplace_products(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'buz_marketplace_stock.action_marketplace_product'
        )
        action['domain'] = [('product_tmpl_id', '=', self.id)]
        action['context'] = {
            'default_product_tmpl_id': self.id,
            'search_default_product_tmpl_id': self.id,
        }
        return action
