from odoo import fields, models


class HelpdeskStage(models.Model):
    _name = 'buz.helpdesk.stage'
    _description = 'Helpdesk Stage'
    _order = 'sequence, name'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    fold = fields.Boolean(string='Fold in Kanban')
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'The stage name must be unique.'),
    ]
