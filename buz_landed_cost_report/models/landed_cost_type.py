from odoo import fields, models


class BuzLandedCostType(models.Model):
    _name = 'buz.landed.cost.type'
    _description = 'Landed Cost Type'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    code = fields.Char()
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'Landed cost type name must be unique.'),
    ]
