# -*- coding: utf-8 -*-
from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    partner_code = fields.Char(
        related='partner_id.partner_code',
        string='Customer Code',
        readonly=True,
        store=False,
        help="Auto-generated partner code of the customer (from Contacts).",
    )
