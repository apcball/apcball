# -*- coding: utf-8 -*-
from odoo import api, fields, models, _, exceptions


class Approvals(models.Model):
    _name = "approvals.approvals"


    user_id = fields.Many2one('res.users', string="User")
    action_date = fields.Datetime('Time')
    rejection_reason = fields.Text()
    sequence = fields.Integer()
    is_approved = fields.Boolean()
    is_rejected = fields.Boolean()
    approver_id = fields.Many2one('team.team')
    active = fields.Boolean(string="Active", default=True)