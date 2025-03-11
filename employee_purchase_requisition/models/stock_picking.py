# -*- coding: utf-8 -*-
from odoo import fields, models


class Picking(models.Model):
    """Class to add new field in stock picking"""

    _inherit = 'stock.picking'

    requisition_order = fields.Char(
        string='Requisition Order',
        help='Requisition order sequence')
