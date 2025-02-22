# -*- coding: utf-8 -*-
from odoo import api, fields, models, _, exceptions


class ResCompany(models.Model):
    _inherit = "res.company"


    approval = fields.Boolean(
        "Sales Order Approval"
    )    


    approval_validation_amount = fields.Monetary(
        string="Minimum Amount for Double Validation", 
        default=5000
    )            
