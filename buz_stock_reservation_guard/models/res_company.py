from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    bypass_reservation_guard_location_ids = fields.Many2many(
        'stock.location',
        'res_company_bypass_reservation_guard_location_rel',
        'company_id',
        'location_id',
        string='Bypass Locations',
        help='Locations where the stock reservation guard is bypassed.',
    )
