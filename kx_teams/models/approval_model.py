# -*- coding: utf-8 -*-
from odoo import api, fields, models, _, exceptions


class ApprovalModel(models.Model):
    _name = "approval.model"
    _description = "Approval Model"  # เพิ่ม description

    name = fields.Char(string="Name", required=True)
    models_ids = fields.Many2many('ir.model', string="Models")