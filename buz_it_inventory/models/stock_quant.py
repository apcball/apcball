from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class BuzItStockQuant(models.Model):
    _name = 'buz.it.stock.quant'
    _description = 'IT Stock On Hand'
    _order = 'inventory_item_id, location_id'

    inventory_item_id = fields.Many2one(
        'buz.it.inventory.item',
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
        ('inventory_item_location_uniq', 'unique(inventory_item_id, location_id)',
         'One stock record per item and location.'),
    ]

    @api.constrains('inventory_item_id', 'location_id')
    def _check_company_consistency(self):
        for record in self:
            if (
                record.inventory_item_id.company_id
                and record.location_id.company_id
                and record.inventory_item_id.company_id
                != record.location_id.company_id
            ):
                raise ValidationError(_(
                    'The inventory item and stock location must belong to the same company.'
                ))

