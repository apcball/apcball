# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    ar_settlement_id = fields.Many2one(
        'ar.settlement', string='AR Settlement', copy=False, index=True,
        readonly=True, ondelete='set null',
        help='Settlement that generated this clearing entry.',
    )
