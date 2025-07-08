# -*- coding: utf-8 -*-
from odoo import fields, models

class PurchaseRequisition(models.Model):
    _inherit = 'purchase.requisition'

    kyld_project_name = fields.Char(string='Project Name')
    pa_type = fields.Char(string='Type')
    plot_number = fields.Char(string='Plot Number')
    date_of_accepting_work = fields.Date(string='Date of Accepting Work')
