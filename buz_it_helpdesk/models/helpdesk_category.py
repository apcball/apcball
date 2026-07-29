from odoo import fields, models


class HelpdeskCategory(models.Model):
    _name = 'buz.helpdesk.category'
    _description = 'Helpdesk Category'
    _order = 'sequence, name'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    description = fields.Text()
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'The category name must be unique.'),
    ]
