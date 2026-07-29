from odoo import fields, models


class HelpdeskTeam(models.Model):
    _name = 'buz.helpdesk.team'
    _description = 'Helpdesk Team'
    _order = 'sequence, name'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    description = fields.Text()
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'The team name must be unique.'),
    ]
