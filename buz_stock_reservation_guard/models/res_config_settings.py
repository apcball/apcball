from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    bypass_reservation_guard_location_ids = fields.Many2many(
        'stock.location',
        string='Bypass Locations',
    )

    @api.model
    def get_values(self):
        res = super().get_values()
        company = self.env.company
        res['bypass_reservation_guard_location_ids'] = [
            (6, 0, company.bypass_reservation_guard_location_ids.ids)
        ]
        return res

    def set_values(self):
        super().set_values()
        self.env.company.write({
            'bypass_reservation_guard_location_ids': [
                (6, 0, self.bypass_reservation_guard_location_ids.ids)
            ],
        })
