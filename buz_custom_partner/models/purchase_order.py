# -*- coding: utf-8 -*-
from odoo import fields, models


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    partner_code = fields.Char(
        related='partner_id.partner_code',
        string='Vendor Code',
        readonly=True,
        store=False,
        help="Auto-generated partner code of the vendor (from Contacts).",
    )
