from odoo import fields, models


class HelpdeskCategory(models.Model):
    _name = 'buz.helpdesk.category'
    _description = 'Helpdesk Category'
    _order = 'sequence, name'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    description = fields.Text()
    type_ids = fields.One2many(
        'buz.helpdesk.category.type', 'category_id', string='Types', copy=True,
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'The category name must be unique.'),
    ]


class HelpdeskCategoryType(models.Model):
    _name = 'buz.helpdesk.category.type'
    _description = 'Helpdesk Category Type'
    _order = 'sequence, name'

    name = fields.Char(required=True)
    category_id = fields.Many2one(
        'buz.helpdesk.category', string='Category', required=True,
        ondelete='cascade', index=True,
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('category_name_uniq', 'unique(category_id, name)',
         'The type name must be unique within its category.'),
    ]
