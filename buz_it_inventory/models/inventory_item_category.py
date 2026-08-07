from odoo import fields, models


class BuzItInventoryItemCategory(models.Model):
    _name = 'buz.it.inventory.item.category'
    _description = 'IT Inventory Item Category'
    _order = 'sequence, name'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    inventory_item_ids = fields.One2many(
        'buz.it.inventory.item', 'category_id', string='Items',
    )

    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'The category name must be unique.'),
    ]

