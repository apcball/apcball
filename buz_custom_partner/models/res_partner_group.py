# -*- coding: utf-8 -*-
from odoo import fields, models


class BuzPartnerGroup(models.Model):
    _name = 'buz.partner.group'
    _description = 'Partner Group'
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
        help="Show this group only on Customer, only on Vendor, or both.",
    )

    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'Partner Group name must be unique!'),
    ]
