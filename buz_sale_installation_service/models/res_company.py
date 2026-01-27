# -*- coding: utf-8 -*-

from odoo import models, fields


class ResCompany(models.Model):
    _inherit = 'res.company'

    default_installation_service_product_id = fields.Many2one(
        'product.product',
        string='Default Installation Service Product',
        domain="[('type', '=', 'service')]",
        help='Default service product for installation fees. Used when product has no specific installation service product.'
    )
