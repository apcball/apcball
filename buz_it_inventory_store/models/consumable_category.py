from odoo import fields, models


class BuzItConsumableCategory(models.Model):
    _name = 'buz.it.consumable.category'
    _description = 'IT Consumable Category'
    _order = 'sequence, name'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    consumable_ids = fields.One2many(
        'buz.it.consumable', 'category_id', string='Items',
    )

    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'The category name must be unique.'),
    ]

