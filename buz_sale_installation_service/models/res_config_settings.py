# -*- coding: utf-8 -*-

from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    default_installation_service_product_id = fields.Many2one(
        'product.product',
        related='company_id.default_installation_service_product_id',
        string='Default Installation Service Product',
        domain="[('type', '=', 'service')]",
        readonly=False,
        store=True,
        default_model='sale.order',
        help='Default service product for installation fees.'
    )
