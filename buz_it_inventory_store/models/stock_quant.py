from odoo import fields, models


class BuzItStockQuant(models.Model):
    _name = 'buz.it.stock.quant'
    _description = 'IT Stock On Hand'
    _order = 'consumable_id, location_id'

    consumable_id = fields.Many2one(
        'buz.it.consumable',
        string='Item',
        required=True,
        ondelete='cascade',
        index=True,
    )
    location_id = fields.Many2one(
        'buz.it.stock.location',
        string='Location',
        required=True,
        ondelete='restrict',
        index=True,
    )
    qty = fields.Float(
        string='Quantity',
        digits=(16, 0),
        required=True,
        default=0.0,
    )
    company_id = fields.Many2one(
        'res.company',
        related='location_id.company_id',
        store=True,
        string='Company',
        index=True,
    )

    _sql_constraints = [
        ('consumable_location_uniq', 'unique(consumable_id, location_id)',
         'One stock record per item and location.'),
    ]

