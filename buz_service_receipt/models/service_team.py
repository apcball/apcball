# -*- coding: utf-8 -*-

from odoo import fields, models


class ServiceTeam(models.Model):
    _name = 'service.team'
    _description = 'Service Team'
    _order = 'name'

    name = fields.Char(string='Team Name', required=True, tracking=True)
    active = fields.Boolean(default=True)
    member_ids = fields.Many2many(
        'res.users',
        'service_team_res_users_rel',
        'team_id',
        'user_id',
        string='Team Members',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
    )

    _sql_constraints = [
        ('name_uniq', 'UNIQUE(name)', 'Team name must be unique!'),
    ]
