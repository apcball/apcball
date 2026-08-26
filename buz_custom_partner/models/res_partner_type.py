# -*- coding: utf-8 -*-
from odoo import fields, models


class BuzPartnerType(models.Model):
    _name = 'buz.partner.type'
    _description = 'Partner Type'
    _order = 'sequence, name'

    name = fields.Char(string='Name', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(string='Active', default=True)
    apply_to = fields.Selection(
        [
            ('customer', 'Customer'),
            ('vendor', 'Vendor'),
            ('both', 'Both'),
        ],
        string='Apply To',
        required=True,
        default='both',
        help="Show this type only on Customer, only on Vendor, or both.",
    )

    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'Partner Type name must be unique!'),
    ]
