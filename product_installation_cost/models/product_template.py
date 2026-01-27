# -*- coding: utf-8 -*-
from odoo import fields, models

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    installation_cost_retail = fields.Monetary(
        string='Installation Cost (Retail)',
        currency_field='currency_id'
    )
    installation_cost_project = fields.Monetary(
        string='Installation Cost (Project)',
        currency_field='currency_id'
    )
