from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


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

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get('buz_quant_write'):
            raise UserError(_(
                'Stock records can only be created through Receive, Issue '
                'or Adjustment.'
            ))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.context.get('buz_quant_write'):
            raise UserError(_(
                'Stock quantities can only be changed through Receive, '
                'Issue or Adjustment.'
            ))
        return super().write(vals)

    def unlink(self):
        raise UserError(_('Stock records cannot be deleted.'))

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
