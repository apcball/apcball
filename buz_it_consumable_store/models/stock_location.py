from odoo import fields, models


class BuzItStockLocation(models.Model):
    _name = 'buz.it.stock.location'
    _description = 'IT Stock Location'
    _order = 'name'

    name = fields.Char(required=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        ondelete='restrict',
    )
    note = fields.Text()
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('name_company_uniq', 'unique(name, company_id)',
         'The location name must be unique within its company.'),
    ]
