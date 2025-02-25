from odoo import api, fields, models

class StockLocation(models.Model):
    _inherit = 'stock.location'

    complete_address = fields.Char(
        string='Complete Address',
        compute='_compute_complete_address',
        store=False
    )

    @api.depends('name', 'location_id')
    def _compute_complete_address(self):
        for location in self:
            address_parts = []
            current_location = location
            while current_location:
                if current_location.name:
                    address_parts.insert(0, current_location.name)
                current_location = current_location.location_id
            location.complete_address = ' / '.join(address_parts)